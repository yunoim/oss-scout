from __future__ import annotations

from scout.audit import AuditResult, Signals
from scout.score import deploy_signals, detect_category, score_candidate
from tests.conftest import NOW, make_candidate


def _ok_audit(name="acme/widget", **kw) -> AuditResult:
    base = dict(full_name=name, license_status="ok", spdx="MIT", license_text_checked=True, readme_fetched=True,
                deps_system="npm", deps_total=10, deps_checked=10,
                signals=Signals(korean_locale=False, has_stripe=True, has_kr_pay=False, has_kr_login=False, auth_mentioned=True, i18n_dirs_checked=["locales"]))
    base.update(kw)
    return AuditResult(**base)


def test_weights_sum_to_100(cfg):
    assert sum(cfg.scoring.weights.values()) == 100


def test_perfect_candidate_hits_100(cfg):
    c = make_candidate(stars=200_000, contributors=500, open_issues=0, language="Go",
                       root_files=["README.md", "LICENSE", "Dockerfile", "docker-compose.yml", ".env.example", "go.mod"])
    sb = score_candidate(c, _ok_audit(), cfg, prev_stars=("2026-W38", 150_000), is_new=False, now=NOW)
    assert sb.total == 100
    assert sb.confidence == "normal"
    assert sb.unknowns == []
    assert set(sb.components) == set(cfg.scoring.weights)
    for k, w in cfg.scoring.weights.items():
        assert sb.components[k] <= w


def test_excluded_is_zero(cfg):
    c = make_candidate()
    a = AuditResult(full_name=c.full_name, license_status="copyleft_or_restricted", excluded=True, exclusion_reason="AGPL")
    sb = score_candidate(c, a, cfg, now=NOW)
    assert sb.total == 0 and sb.excluded and sb.exclusion_reason == "AGPL"
    assert all(v == 0 for v in sb.components.values())


def test_restricted_terms_and_copyleft_deps_zero_license(cfg):
    c = make_candidate()
    sb1 = score_candidate(c, _ok_audit(restricted_terms=["multi-tenant"]), cfg, now=NOW)
    sb2 = score_candidate(c, _ok_audit(copyleft_deps=["x (GPL-3.0)"]), cfg, now=NOW)
    assert sb1.components["license"] == 0 and sb2.components["license"] == 0
    assert not sb1.excluded


def test_ee_dir_penalty_and_unknown_license(cfg):
    c = make_candidate()
    w = cfg.scoring.weights["license"]
    assert score_candidate(c, _ok_audit(), cfg, now=NOW).components["license"] == w
    assert score_candidate(c, _ok_audit(has_ee_dir=True), cfg, now=NOW).components["license"] == w * 15 / 20
    assert score_candidate(c, _ok_audit(license_status="unknown"), cfg, now=NOW).components["license"] == w * 8 / 20


def test_first_week_uses_stars_only(cfg):
    c = make_candidate(stars=10_000)
    sb = score_candidate(c, _ok_audit(), cfg, prev_stars=None, is_new=True, now=NOW)
    assert sb.stars_delta is None and sb.growth_ratio is None
    assert any("no star history" in n for n in sb.notes)
    assert sb.components["popularity"] > 0
    assert sb.is_new


def test_growth_from_history(cfg):
    c = make_candidate(stars=10_500)
    sb_up = score_candidate(c, _ok_audit(), cfg, prev_stars=("2026-W38", 10_000), is_new=False, now=NOW)
    sb_flat = score_candidate(c, _ok_audit(), cfg, prev_stars=("2026-W38", 10_500), is_new=False, now=NOW)
    assert sb_up.stars_delta == 500 and abs(sb_up.growth_ratio - 0.05) < 1e-9
    assert sb_up.components["popularity"] > sb_flat.components["popularity"]
    assert not sb_up.is_new


def test_low_confidence_when_many_unknowns(cfg):
    c = make_candidate(contributors=None)
    c.releases_fetched = False
    a = _ok_audit(license_status="unknown", deps_system=None, deps_total=0, deps_checked=0)
    sb = score_candidate(c, a, cfg, now=NOW)
    assert {"license", "contributors", "releases", "deps"} <= set(sb.unknowns)
    assert sb.confidence == "low"


def test_korea_points_and_models(cfg):
    c = make_candidate(topics=["analytics", "self-hosted"])
    sb = score_candidate(c, _ok_audit(), cfg, now=NOW)
    assert sb.korea_points == 10  # no ko locale +4, stripe w/o kr pay +3, no kakao/naver login +3
    assert sb.category == "analytics"
    assert "managed-hosting" in sb.models and "korean-localization" in sb.models
    a_kr = _ok_audit(signals=Signals(korean_locale=True, has_stripe=True, has_kr_pay=True, has_kr_login=True, auth_mentioned=True))
    assert score_candidate(c, a_kr, cfg, now=NOW).korea_points == 0


def test_category_detection_and_models(cfg):
    assert detect_category(make_candidate(topics=["crm", "sales"], description="Open source CRM"), cfg)[0] == "crm"
    assert detect_category(make_candidate(topics=["cli", "devops"], description="A CLI tool"), cfg) == ("devtool", 5)
    assert detect_category(make_candidate(topics=[], description="Something odd"), cfg) == ("other", cfg.scoring.category.default_weight)
    cms = make_candidate(topics=["cms"], description="headless cms")
    sb = score_candidate(cms, _ok_audit(), cfg, now=NOW)
    assert "si-onprem" in sb.models
    dev = make_candidate(topics=["cli"], description="cli tool")
    assert "template-sale" in score_candidate(dev, _ok_audit(), cfg, now=NOW).models


def test_library_demoted_even_with_llm_topics(cfg):
    lib = make_candidate(topics=["llm", "rag", "agents", "framework"], description="Data framework for LLM applications")
    assert detect_category(lib, cfg) == ("lib", 5)
    app = make_candidate(topics=["llm", "rag", "self-hosted", "framework"], description="Self-hosted RAG app")
    assert detect_category(app, cfg)[0] == "llm-workflow"


def test_plugin_sale_tag(cfg):
    big = make_candidate(stars=30_000, root_dirs=["src", "plugins"])
    small = make_candidate(stars=3_000, root_dirs=["src", "plugins"])
    none = make_candidate(stars=30_000, root_dirs=["src"])
    assert "plugin-sale" in score_candidate(big, _ok_audit(), cfg, now=NOW).models
    assert "plugin-sale" not in score_candidate(small, _ok_audit(), cfg, now=NOW).models
    assert "plugin-sale" not in score_candidate(none, _ok_audit(), cfg, now=NOW).models


def test_deploy_signals():
    c = make_candidate(language="Rust", root_files=["Dockerfile.dev", "compose.yaml", "Cargo.toml"], root_dirs=["helm"])
    ds = deploy_signals(c)
    assert ds == {"dockerfile": True, "compose": True, "helm_or_env": True, "single_binary": True}
    assert not any(deploy_signals(make_candidate(root_files=["README.md"], root_dirs=[])).values())


def test_next_action_priorities(cfg):
    c = make_candidate()
    assert "ee 폴더" in score_candidate(c, _ok_audit(has_ee_dir=True), cfg, now=NOW).next_action
    assert "리브랜딩" in score_candidate(c, _ok_audit(trademark_notice=True), cfg, now=NOW).next_action
    assert "한국어" in score_candidate(c, _ok_audit(), cfg, now=NOW).next_action
