"""Monetization score (0-100) with per-component breakdown, model tags and next action."""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone

from pydantic import BaseModel

from .audit import AuditResult
from .config import Config
from .discover import Candidate

COMPOSE_RE = re.compile(r"^(docker-)?compose([.-].*)?\.ya?ml$", re.I)
HELM_DIRS = {"helm", "charts", "chart", "k8s", "kubernetes", "kube", "deploy", "deployment", "deployments"}
ENV_FILES = {".env.example", ".env.sample", ".env.template", ".env.dist", "env.example"}


class ScoreBreakdown(BaseModel):
    full_name: str
    total: int = 0
    excluded: bool = False
    exclusion_reason: str | None = None
    components: dict[str, float] = {}
    category: str = "other"
    category_weight: int = 8
    models: list[str] = []
    korea_points: int = 0
    confidence: str = "normal"
    unknowns: list[str] = []
    stars_delta: int | None = None
    growth_ratio: float | None = None
    is_new: bool = True
    notes: list[str] = []
    next_action: str = ""


# ------------------------------------------------------------------ helpers
def detect_category(c: Candidate, cfg: Config) -> tuple[str, int]:
    cat_cfg = cfg.scoring.category
    text_desc = (c.description or "").lower()
    name_tokens = set(re.split(r"[^a-z0-9]+", c.name.lower()))
    desc_tokens = set(re.split(r"[^a-z0-9]+", text_desc))
    topics = set(c.topics)
    best: tuple[int, int, str] | None = None  # (score, weight, category)
    for cat, kws in cat_cfg.keywords.items():
        s = 0
        for kw in kws:
            k = kw.lower()
            if k in topics:
                s += 3
            if k in name_tokens:
                s += 2
            if k in desc_tokens or (" " in k and k in text_desc):
                s += 1
        if s:
            w = cat_cfg.weights.get(cat, cat_cfg.default_weight)
            cand = (s, w, cat)
            if best is None or cand[:2] > best[:2]:
                best = cand
    if not best:
        return "other", cat_cfg.default_weight
    return best[2], best[1]


def deploy_signals(c: Candidate) -> dict[str, bool]:
    files = {f.lower() for f in c.root_files}
    dirs = {d.lower() for d in c.root_dirs}
    dockerfile = any(f.startswith("dockerfile") for f in files) or "docker" in dirs
    compose = any(COMPOSE_RE.match(f) for f in c.root_files)
    helm_or_env = bool(dirs & HELM_DIRS) or bool(files & ENV_FILES)
    single_binary = (c.language or "").lower() in ("go", "rust") and ({"go.mod", "cargo.toml"} & files) != set()
    return {"dockerfile": dockerfile, "compose": compose, "helm_or_env": helm_or_env, "single_binary": single_binary}


def plugin_dir(c: Candidate, cfg: Config) -> str | None:
    """Name of a root-level plugin/extension directory, if any (no API call: uses the root listing)."""
    wanted = {d.lower() for d in cfg.scoring.models.plugin_dirs}
    for d in c.root_dirs:
        if d.lower() in wanted:
            return d
    return None


def _scale(raw: float, raw_max: float, weight: int) -> float:
    if raw_max <= 0:
        return 0.0
    return round(max(0.0, min(raw, raw_max)) / raw_max * weight, 2)


# ------------------------------------------------------------------ main
def score_candidate(
    c: Candidate,
    a: AuditResult,
    cfg: Config,
    prev_stars: tuple[str, int] | None = None,
    is_new: bool = True,
    now: datetime | None = None,
) -> ScoreBreakdown:
    now = now or datetime.now(timezone.utc)
    sc = cfg.scoring
    W = sc.weights
    sb = ScoreBreakdown(full_name=c.full_name, is_new=is_new)
    sb.category, sb.category_weight = detect_category(c, cfg)

    if prev_stars:
        _w, prev = prev_stars
        sb.stars_delta = c.stars - prev
        sb.growth_ratio = (c.stars - prev) / prev if prev > 0 else None

    # hard exclusions -> 0
    if a.excluded or a.license_status == "copyleft_or_restricted":
        sb.excluded = True
        sb.exclusion_reason = a.exclusion_reason or "copyleft_or_restricted"
        sb.total = 0
        sb.components = {k: 0.0 for k in W}
        sb.next_action = "제외 — 라이선스 사유 확인"
        return sb

    unknowns: list[str] = []
    notes: list[str] = []

    # 1. license cleanliness
    lc = sc.license
    if a.restricted_terms or a.copyleft_deps:
        lic_raw = 0
        notes.append("restricted terms / copyleft deps → license 0")
    elif a.license_status == "ok":
        lic_raw = lc.ok
    else:
        lic_raw = lc.unknown
        unknowns.append("license")
    if a.has_ee_dir:
        lic_raw = max(0, lic_raw - lc.ee_dir_penalty)
        notes.append(f"ee dir -{lc.ee_dir_penalty}")
    sb.components["license"] = _scale(lic_raw, lc.ok, W["license"])

    # 2. activity
    ac = sc.activity
    act_raw = 0
    if c.pushed_at and (now - c.pushed_at).days <= ac.recent_push_days:
        act_raw += ac.recent_push_points
    if not c.releases_fetched:
        unknowns.append("releases")
    elif c.latest_release_at and (now - c.latest_release_at).days <= ac.release_within_days:
        act_raw += ac.release_points
    sb.components["activity"] = _scale(act_raw, ac.recent_push_points + ac.release_points, W["activity"])

    # 3. popularity & momentum
    pc = sc.popularity
    log_norm = min(math.log10(max(c.stars, 1)) / pc.log_stars_max, 1.0)
    if sb.growth_ratio is None:
        pop_raw = log_norm * (pc.log_stars_points + pc.growth_points)  # first week: stars only
        notes.append("no star history → stars only")
    else:
        growth_norm = max(0.0, min(sb.growth_ratio / pc.growth_full_ratio, 1.0))
        pop_raw = log_norm * pc.log_stars_points + growth_norm * pc.growth_points
    sb.components["popularity"] = _scale(pop_raw, pc.log_stars_points + pc.growth_points, W["popularity"])

    # 4. community health
    cc = sc.community
    com_raw = 0.0
    if c.contributors is None:
        unknowns.append("contributors")
    elif c.contributors >= cc.contributors_threshold:
        com_raw += cc.contributors_points
    ratio = c.open_issues / c.stars if c.stars else 1.0
    com_raw += cc.issue_ratio_points * (1 - min(ratio / cc.issue_ratio_bad, 1.0))
    sb.components["community"] = _scale(com_raw, cc.contributors_points + cc.issue_ratio_points, W["community"])

    # 5. deployability
    dc = sc.deploy
    ds = deploy_signals(c)
    dep_raw = (
        (dc.dockerfile if ds["dockerfile"] else 0)
        + (dc.compose if ds["compose"] else 0)
        + (dc.helm_or_env if ds["helm_or_env"] else 0)
        + (dc.single_binary if ds["single_binary"] else 0)
    )
    sb.components["deploy"] = _scale(dep_raw, dc.dockerfile + dc.compose + dc.helm_or_env + dc.single_binary, W["deploy"])

    # 6. category marketability
    cat_max = max(max(sc.category.weights.values(), default=0), sc.category.default_weight)
    sb.components["category"] = _scale(sb.category_weight, cat_max, W["category"])

    # 7. korea opportunity
    kc = sc.korea
    sig = a.signals
    kr = 0
    if sig.korean_locale is not True:
        kr += kc.no_korean_locale
        if sig.korean_locale is None and not sig.i18n_dirs_checked and not a.readme_fetched:
            unknowns.append("korea")
    if sig.has_stripe and not sig.has_kr_pay:
        kr += kc.stripe_without_kr_pay
    if not sig.has_kr_login and (sig.auth_mentioned or sb.category in sc.models.saas_categories):
        kr += kc.no_kr_social_login
    sb.korea_points = kr
    sb.components["korea"] = _scale(kr, kc.no_korean_locale + kc.stripe_without_kr_pay + kc.no_kr_social_login, W["korea"])

    # deps unknown counts toward confidence
    if a.deps_system is None or (a.deps_checked and a.unknown_deps * 2 > a.deps_checked):
        unknowns.append("deps")

    sb.total = int(round(sum(sb.components.values())))
    sb.total = max(0, min(100, sb.total))
    sb.unknowns = unknowns
    sb.confidence = "low" if len(unknowns) >= sc.confidence_low_unknowns else "normal"
    sb.notes = notes

    # model tags
    m = sc.models
    models: list[str] = []
    if ds["compose"] and sb.category in m.saas_categories:
        models.append("managed-hosting")
    if sb.category in m.onprem_categories:
        models.append("si-onprem")
    if kr >= m.korea_threshold:
        models.append("korean-localization")
    if sb.category == "devtool":
        models.append("template-sale")
    pdir = plugin_dir(c, cfg)
    if pdir and c.stars >= m.plugin_min_stars:
        models.append("plugin-sale")
        notes.append(f"plugin ecosystem: {pdir}/")
    sb.models = models

    sb.next_action = next_action(a, sb)
    return sb


def next_action(a: AuditResult, sb: ScoreBreakdown) -> str:
    actions: list[str] = []
    if a.has_ee_dir:
        actions.append("ee 폴더 라이선스 확인")
    if a.trademark_notice:
        actions.append("리브랜딩 필요(상표 고지)")
    if a.license_status == "unknown":
        actions.append("LICENSE 원문 직접 확인")
    if a.copyleft_deps:
        actions.append("copyleft 의존성 교체 검토")
    if a.deps_checked and a.unknown_deps * 2 > a.deps_checked:
        actions.append("의존성 라이선스 수동 확인")
    if a.readme_terms:
        actions.append("README 제한 문구 맥락 확인")
    if not actions:
        if "korean-localization" in sb.models:
            actions.append("한국어 로컬라이즈 + 국내 결제 PoC")
        elif "managed-hosting" in sb.models:
            actions.append("compose 배포 데모 후 수요 검증")
        else:
            actions.append("데모 배포 후 수요 검증")
    return " · ".join(actions[:2])
