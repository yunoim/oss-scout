"""License, dependency, ee-folder, trademark and Korea-signal audit for one candidate."""
from __future__ import annotations

import json
import logging
import re
import threading
import tomllib
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from pydantic import BaseModel

from .config import Config
from .discover import Candidate
from .github_client import GitHubClient

log = logging.getLogger(__name__)

LicenseStatus = Literal["ok", "unknown", "copyleft_or_restricted"]

# Root-license patterns that positively identify a permissive license when GitHub says NOASSERTION.
PERMISSIVE_TEXT_PATTERNS: dict[str, str] = {
    "MIT": r"Permission is hereby granted, free of charge, to any person obtaining a copy",
    "Apache-2.0": r"Apache License\s*,?\s*Version 2\.0",
    "BSD-3-Clause": r"Redistribution and use in source and binary forms.*?Neither the name",
    "BSD-2-Clause": r"Redistribution and use in source and binary forms",
    "ISC": r"ISC License|Permission to use, copy, modify, and(/or)? distribute this software for any purpose",
    "Unlicense": r"This is free and unencumbered software released into the public domain",
}

# README-only matches of these are informational (feature descriptions), not license restrictions.
WEAK_README_TERMS = {"multi-tenant", "multitenant", "enterprise edition"}

KR_PAY_RE = re.compile(r"toss ?payments?|tosspayments|kakao ?pay|naver ?pay|payco|iamport|portone|nicepay|kg ?inicis", re.I)
STRIPE_RE = re.compile(r"\bstripe\b", re.I)
KR_LOGIN_RE = re.compile(r"kakao|naver", re.I)
AUTH_RE = re.compile(r"\b(oauth|sso|social login|sign[- ]?in with|login with|google login|github login|authentication)\b", re.I)
KOREAN_TEXT_RE = re.compile(r"한국어|korean|[가-힣]{2,}", re.I)


class Signals(BaseModel):
    i18n_dirs_checked: list[str] = []
    korean_locale: bool | None = None  # None = could not determine
    has_stripe: bool = False
    has_kr_pay: bool = False
    has_kr_login: bool = False
    auth_mentioned: bool = False


class AuditResult(BaseModel):
    full_name: str
    license_status: LicenseStatus = "unknown"
    spdx: str | None = None
    license_text_checked: bool = False
    restricted_terms: list[str] = []
    readme_terms: list[str] = []  # weak README-only mentions (informational)
    has_ee_dir: bool = False
    ee_dirs: list[str] = []
    ee_license_excerpt: str | None = None
    extra_license_files: list[str] = []
    deps_system: str | None = None
    deps_total: int = 0
    deps_checked: int = 0
    copyleft_deps: list[str] = []
    unknown_deps: int = 0
    trademark_notice: bool = False
    readme_fetched: bool = False
    excluded: bool = False
    exclusion_reason: str | None = None
    signals: Signals = Signals()

    def flags(self) -> list[str]:
        out: list[str] = []
        if self.has_ee_dir:
            out.append("ee_dir")
        if self.trademark_notice:
            out.append("trademark")
        if self.restricted_terms:
            out.append("restricted_terms")
        if self.copyleft_deps:
            out.append("copyleft_deps")
        if self.license_status == "unknown" or (self.deps_total and self.unknown_deps * 2 > self.deps_checked):
            out.append("unknown")
        if self.readme_terms:
            out.append("readme_terms")
        return out


# ------------------------------------------------------------------ manifests
_VER_RE = re.compile(r"^v?\d+\.\d+\.\d+([-+][0-9A-Za-z.]+)?$")


def _clean_version(v: str | None) -> str | None:
    if not v or not isinstance(v, str):
        return None
    v = v.strip()
    if v.startswith(("workspace:", "npm:", "file:", "link:", "git", "http", "github:")):
        return None
    v = re.sub(r"^[~^=v<>\s]+", "", v)
    v = v.split(" ")[0].split("||")[0].strip()
    return v if _VER_RE.match(v) else None


def parse_package_json(text: str) -> list[tuple[str, str | None]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    deps = data.get("dependencies") or {}
    out: list[tuple[str, str | None]] = []
    for name, ver in deps.items():
        if isinstance(ver, str) and ver.startswith(("workspace:", "file:", "link:")):
            continue  # internal monorepo package
        out.append((name, _clean_version(ver)))
    return out


_PEP508_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
_PEP508_PIN = re.compile(r"==\s*([0-9][0-9A-Za-z.\-+]*)")


def _parse_pep508(line: str) -> tuple[str, str | None] | None:
    line = line.split("#")[0].strip()
    if not line or line.startswith(("-", "git+", "http://", "https://", ".", "/")):
        return None
    m = _PEP508_NAME.match(line)
    if not m:
        return None
    name = m.group(1).lower().replace("_", "-")
    pin = _PEP508_PIN.search(line)
    return name, (pin.group(1) if pin else None)


def parse_pyproject(text: str) -> list[tuple[str, str | None]]:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return []
    out: list[tuple[str, str | None]] = []
    for dep in (data.get("project") or {}).get("dependencies") or []:
        p = _parse_pep508(dep)
        if p:
            out.append(p)
    poetry = ((data.get("tool") or {}).get("poetry") or {}).get("dependencies") or {}
    for name, spec in poetry.items():
        if name.lower() == "python":
            continue
        ver = spec if isinstance(spec, str) else (spec.get("version") if isinstance(spec, dict) else None)
        out.append((name.lower().replace("_", "-"), _clean_version(ver)))
    return out


def parse_requirements(text: str) -> list[tuple[str, str | None]]:
    out = []
    for line in text.splitlines():
        p = _parse_pep508(line)
        if p:
            out.append(p)
    return out


def parse_go_mod(text: str) -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    in_block = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("require ("):
            in_block = True
            continue
        if in_block and line.startswith(")"):
            in_block = False
            continue
        if "// indirect" in line:
            continue
        m = None
        if in_block:
            m = re.match(r"^(\S+)\s+(\S+)", line)
        elif line.startswith("require "):
            m = re.match(r"^require\s+(\S+)\s+(\S+)", line)
        if m and "/" in m.group(1):
            out.append((m.group(1), m.group(2)))
    return out


def parse_cargo_toml(text: str) -> list[tuple[str, str | None]]:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return []
    out: list[tuple[str, str | None]] = []
    deps = data.get("dependencies") or {}
    if not deps and "workspace" in data:
        deps = (data["workspace"] or {}).get("dependencies") or {}
    for name, spec in deps.items():
        if isinstance(spec, dict) and (spec.get("path") or spec.get("git")) and not spec.get("version"):
            continue
        ver = spec if isinstance(spec, str) else (spec.get("version") if isinstance(spec, dict) else None)
        pkg = spec.get("package", name) if isinstance(spec, dict) else name
        out.append((pkg, _clean_version(ver)))
    return out


MANIFESTS: list[tuple[str, str, object]] = [
    ("package.json", "npm", parse_package_json),
    ("pyproject.toml", "pypi", parse_pyproject),
    ("requirements.txt", "pypi", parse_requirements),
    ("go.mod", "go", parse_go_mod),
    ("Cargo.toml", "cargo", parse_cargo_toml),
]


# ------------------------------------------------------------------ license helpers
def _license_family(spdx: str) -> str:
    return spdx.upper().split("-")[0]


def classify_spdx(spdx: str | None, cfg: Config) -> LicenseStatus | None:
    """Classify from GitHub's spdx_id alone. None means 'need the text'."""
    if not spdx or spdx.upper() in ("NOASSERTION", "OTHER"):
        return None
    if spdx in cfg.audit.ok_licenses:
        return "ok"
    families = {_license_family(x) for x in cfg.audit.copyleft_spdx}
    if spdx in cfg.audit.copyleft_spdx or _license_family(spdx) in families:
        return "copyleft_or_restricted"
    return None


def classify_text(text: str, cfg: Config) -> tuple[LicenseStatus, str | None]:
    """Classify a LICENSE body. Returns (status, inferred spdx)."""
    text = " ".join(text.split())
    for pat in cfg.audit.copyleft_patterns:
        if re.search(pat, text, re.I):
            return "copyleft_or_restricted", None
    for spdx, pat in PERMISSIVE_TEXT_PATTERNS.items():
        if re.search(pat, text, re.I | re.S):
            return "ok", spdx
    return "unknown", None


def find_restricted_terms(text: str, cfg: Config) -> list[str]:
    text = " ".join(text.split())  # license texts are hard-wrapped; match across line breaks
    hits = []
    for pat in cfg.audit.restricted_term_patterns:
        if re.search(pat, text, re.I):
            hits.append(pat)
    return hits


def dep_is_copyleft(licenses: list[str], cfg: Config) -> bool:
    """A dependency is copyleft when every license alternative is copyleft."""
    if not licenses:
        return False
    pat = re.compile(cfg.audit.dep_copyleft_pattern)
    for expr in licenses:
        alternatives = re.split(r"\s+OR\s+", expr.strip("() "), flags=re.I)
        if not all(pat.search(alt) for alt in alternatives):
            return False
    return True


# ------------------------------------------------------------------ main audit
class Auditor:
    def __init__(self, client: GitHubClient, cfg: Config, dep_workers: int = 8):
        self.client = client
        self.cfg = cfg
        self.dep_workers = dep_workers
        self._dep_cache: dict[tuple[str, str, str | None], list[str] | None] = {}
        self._dep_lock = threading.Lock()

    # --- dependencies
    def _lookup_dep(self, system: str, name: str, version: str | None) -> list[str] | None:
        key = (system, name, version)
        with self._dep_lock:
            if key in self._dep_cache:
                return self._dep_cache[key]
        try:
            res = self.client.depsdev_licenses(system, name, version)
        except Exception as e:  # noqa: BLE001
            log.debug("deps.dev lookup failed %s/%s: %s", system, name, e)
            res = None
        if res is None and version:  # pinned version missing upstream -> try default version
            try:
                res = self.client.depsdev_licenses(system, name, None)
            except Exception:  # noqa: BLE001
                res = None
        with self._dep_lock:
            self._dep_cache[key] = res
        return res

    def scan_dependencies(self, c: Candidate, result: AuditResult) -> None:
        for fname, system, parser in MANIFESTS:
            if fname not in c.root_files:
                continue
            text = self.client.file_text(c.full_name, fname, ref=c.default_branch)
            if not text:
                continue
            deps = parser(text)  # type: ignore[operator]
            if not deps:
                continue
            result.deps_system = system
            result.deps_total = len(deps)
            deps = deps[: self.cfg.audit.max_deps]
            result.deps_checked = len(deps)
            with ThreadPoolExecutor(max_workers=self.dep_workers) as pool:
                results = list(pool.map(lambda d: self._lookup_dep(system, d[0], d[1]), deps))
            for (name, _ver), lics in zip(deps, results):
                if lics is None:
                    result.unknown_deps += 1
                elif dep_is_copyleft(lics, self.cfg):
                    result.copyleft_deps.append(f"{name} ({' / '.join(lics)})")
            self._collect_dep_signals(deps, result.signals)
            return  # first manifest found wins

    @staticmethod
    def _collect_dep_signals(deps: list[tuple[str, str | None]], sig: Signals) -> None:
        names = " ".join(n.lower() for n, _ in deps)
        if STRIPE_RE.search(names):
            sig.has_stripe = True
        if KR_PAY_RE.search(names):
            sig.has_kr_pay = True
        if re.search(r"kakao|naver", names):
            sig.has_kr_login = True
        if re.search(r"passport|next-auth|auth|oauth|oidc|keycloak|lucia|clerk|supabase", names):
            sig.auth_mentioned = True

    # --- ee dirs
    def scan_ee_dirs(self, c: Candidate, result: AuditResult) -> None:
        names = {n.lower() for n in self.cfg.audit.ee_dir_names}
        found = [d for d in c.root_dirs if d.lower() in names]
        for parent in self.cfg.audit.ee_parent_dirs:
            if parent in c.root_dirs:
                sub = self.client.contents(c.full_name, parent, ref=c.default_branch) or []
                found += [f"{parent}/{e['name']}" for e in sub if e.get("type") == "dir" and e["name"].lower() in names]
        extra = [f for f in c.root_files if re.search(r"licen[sc]e", f, re.I) and re.search(r"ee|enterprise|commercial|premium", f, re.I)]
        result.extra_license_files = extra
        if not found and not extra:
            return
        result.has_ee_dir = True
        result.ee_dirs = found
        for d in found[:2]:
            listing = self.client.contents(c.full_name, d, ref=c.default_branch) or []
            lic = next((e for e in listing if e.get("type") == "file" and re.match(r"licen[sc]e", e["name"], re.I)), None)
            if lic:
                text = self.client.file_text(c.full_name, f"{d}/{lic['name']}", ref=c.default_branch, max_bytes=4000)
                if text:
                    result.ee_license_excerpt = " ".join(text[:200].split())
                    return
        if extra and not result.ee_license_excerpt:
            text = self.client.file_text(c.full_name, extra[0], ref=c.default_branch, max_bytes=4000)
            if text:
                result.ee_license_excerpt = " ".join(text[:200].split())

    # --- korea signals
    @staticmethod
    def _is_korean_entry(name: str, markers: list[str]) -> bool:
        n = name.lower()
        stem = n.split(".")[0]
        return n in markers or stem in ("ko", "ko-kr", "ko_kr", "kor", "korean") or n.startswith(("ko.", "ko-", "ko_"))

    def scan_i18n(self, c: Candidate, sig: Signals) -> None:
        kc = self.cfg.scoring.korea
        markers = [m.lower() for m in kc.korean_locale_markers]
        nested_names = {"locales", "locale", "lang", "langs", "messages", "translations", "i18n", "intl", "language", "languages"}
        checked = 0
        korean = False
        for path in kc.i18n_dirs:
            top = path.split("/")[0]
            if top not in c.root_dirs:
                continue
            listing = self.client.contents(c.full_name, path, ref=c.default_branch)
            if listing is None:
                continue
            checked += 1
            sig.i18n_dirs_checked.append(path)
            korean = korean or any(self._is_korean_entry(e["name"], markers) for e in listing)
            # one level of nesting, e.g. src/i18n/locales/ko.json
            if not korean:
                for sub in (e for e in listing if e.get("type") == "dir" and e["name"].lower() in nested_names):
                    sub_path = f"{path}/{sub['name']}"
                    sub_listing = self.client.contents(c.full_name, sub_path, ref=c.default_branch)
                    if sub_listing is not None:
                        checked += 1
                        sig.i18n_dirs_checked.append(sub_path)
                        korean = korean or any(self._is_korean_entry(e["name"], markers) for e in sub_listing)
                    break
            if korean or checked >= kc.max_i18n_listings:
                break
        if checked:
            sig.korean_locale = korean

    # --- entry point
    def audit(self, c: Candidate, skip_deps: bool = False) -> AuditResult:
        cfg = self.cfg
        spdx0 = c.license_spdx if c.license_spdx and c.license_spdx.upper() not in ("NOASSERTION", "OTHER") else None
        res = AuditResult(full_name=c.full_name, spdx=spdx0)

        trap = cfg.known_traps.get(c.full_name.lower())
        if trap:
            res.excluded = True
            res.exclusion_reason = f"known_trap: {trap}"
            res.license_status = "copyleft_or_restricted"
            return res

        # 1. root license
        status = classify_spdx(c.license_spdx, cfg)
        detected_spdx, lic_text = self.client.license_file(c.full_name)
        if detected_spdx and detected_spdx.upper() not in ("NOASSERTION", "OTHER"):
            res.spdx = detected_spdx
            if status is None:
                status = classify_spdx(detected_spdx, cfg)
        if lic_text:
            res.license_text_checked = True
            text_status, inferred = classify_text(lic_text, cfg)
            if status is None:
                status = text_status
                if inferred and not res.spdx:
                    res.spdx = inferred
            elif status == "ok" and text_status == "copyleft_or_restricted":
                status = "copyleft_or_restricted"  # GitHub mis-detected; text wins
        res.license_status = status or "unknown"

        # 2. restricted terms (LICENSE strong; README strong-only)
        readme = self.client.readme_text(c.full_name)
        res.readme_fetched = readme is not None
        hits: list[str] = []
        if lic_text:
            hits += find_restricted_terms(lic_text, cfg)
        if readme:
            for pat in find_restricted_terms(readme, cfg):
                if pat.lower() in WEAK_README_TERMS:
                    res.readme_terms.append(pat)
                else:
                    hits.append(pat)
            if any(re.search(p, readme, re.I) for p in cfg.audit.trademark_patterns):
                res.trademark_notice = True
            if KOREAN_TEXT_RE.search(readme):
                res.signals.korean_locale = True
            if STRIPE_RE.search(readme):
                res.signals.has_stripe = True
            if KR_PAY_RE.search(readme):
                res.signals.has_kr_pay = True
            if KR_LOGIN_RE.search(readme):
                res.signals.has_kr_login = True
            if AUTH_RE.search(readme):
                res.signals.auth_mentioned = True
        res.restricted_terms = sorted(set(hits))
        res.readme_terms = sorted(set(res.readme_terms))

        if res.license_status == "copyleft_or_restricted":
            res.excluded = True
            res.exclusion_reason = f"copyleft_or_restricted: {res.spdx or 'license text'}"
            return res

        # 3. ee dirs, 4. deps, 5. i18n
        self.scan_ee_dirs(c, res)
        if not skip_deps:
            self.scan_dependencies(c, res)
        if res.signals.korean_locale is not True:
            self.scan_i18n(c, res.signals)
        return res
