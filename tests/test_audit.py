from __future__ import annotations

import httpx
import respx

from scout.audit import (
    Auditor,
    classify_text,
    dep_is_copyleft,
    parse_cargo_toml,
    parse_go_mod,
    parse_package_json,
    parse_pyproject,
    parse_requirements,
)
from tests.conftest import AGPL_TEXT, APACHE_PLUS_TEXT, MIT_TEXT, SUL_TEXT, GitHubMock, depsdev, depsdev_default, make_candidate


def _router():
    return respx.mock(assert_all_called=False, assert_all_mocked=True)


def _audit(client, cfg, gh: GitHubMock, c):
    gh.fallback()
    return Auditor(client, cfg).audit(c)


def test_mit_clean(cfg, client):
    c = make_candidate()
    with _router() as r:
        gh = GitHubMock(r, c.full_name).license("MIT", MIT_TEXT).readme().package_json({"react": "^18.2.0", "workspace-pkg": "workspace:*"})
        depsdev(r, "npm", "react", "18.2.0", ["MIT"])
        res = _audit(client, cfg, gh, c)
    assert res.license_status == "ok"
    assert res.spdx == "MIT"
    assert res.restricted_terms == []
    assert res.copyleft_deps == []
    assert res.deps_checked == 1  # workspace dep skipped
    assert not res.excluded
    assert res.flags() == []


def test_apache_with_additional_conditions(cfg, client):
    c = make_candidate(spdx="Apache-2.0", root_files=["README.md", "LICENSE"])
    with _router() as r:
        gh = GitHubMock(r, c.full_name).license("Apache-2.0", APACHE_PLUS_TEXT).readme()
        res = _audit(client, cfg, gh, c)
    assert res.license_status == "ok"  # root license itself is permissive...
    assert res.restricted_terms  # ...but additional conditions are flagged
    assert any("multi-tenant" in t for t in res.restricted_terms)
    assert any("express written permission" in t for t in res.restricted_terms)
    assert "restricted_terms" in res.flags()
    assert not res.excluded  # exclusion happens at scoring (0 points), not here


def test_agpl_excluded(cfg, client):
    c = make_candidate(spdx="AGPL-3.0", root_files=["README.md", "LICENSE"])
    with _router() as r:
        gh = GitHubMock(r, c.full_name).license("AGPL-3.0", AGPL_TEXT).readme()
        res = _audit(client, cfg, gh, c)
    assert res.license_status == "copyleft_or_restricted"
    assert res.excluded
    assert "AGPL" in (res.exclusion_reason or "")


def test_noassertion_sustainable_use_text(cfg, client):
    c = make_candidate(full_name="acme/flow", spdx="NOASSERTION", root_files=["README.md", "LICENSE.md"])
    with _router() as r:
        gh = GitHubMock(r, c.full_name).license("NOASSERTION", SUL_TEXT).readme()
        res = _audit(client, cfg, gh, c)
    assert res.license_status == "copyleft_or_restricted"
    assert res.excluded


def test_noassertion_but_mit_text_is_ok(cfg, client):
    c = make_candidate(spdx="NOASSERTION", root_files=["README.md", "LICENSE"])
    with _router() as r:
        gh = GitHubMock(r, c.full_name).license("NOASSERTION", MIT_TEXT).readme()
        res = _audit(client, cfg, gh, c)
    assert res.license_status == "ok"
    assert res.spdx == "MIT"


def test_unknown_when_no_license_text(cfg, client):
    c = make_candidate(spdx=None, root_files=["README.md"])
    with _router() as r:
        gh = GitHubMock(r, c.full_name).license(None, None).readme()
        res = _audit(client, cfg, gh, c)
    assert res.license_status == "unknown"
    assert "unknown" in res.flags()
    assert not res.excluded


def test_known_trap(cfg, client):
    c = make_candidate(full_name="n8n-io/n8n", spdx="NOASSERTION")
    with _router():
        res = Auditor(client, cfg).audit(c)  # no HTTP calls at all
    assert res.excluded
    assert "Sustainable Use" in res.exclusion_reason


def test_ee_dir_detected(cfg, client):
    c = make_candidate(root_files=["README.md", "LICENSE"], root_dirs=["src", "ee", "packages"])
    with _router() as r:
        gh = GitHubMock(r, c.full_name).license("MIT", MIT_TEXT).readme()
        gh.contents("packages", [("core", "dir"), ("ee", "dir")])
        gh.contents("ee", [("LICENSE", "file"), ("src", "dir")])
        gh.file("ee/LICENSE", "The Enterprise Edition is licensed under a commercial license. Contact sales.")
        res = _audit(client, cfg, gh, c)
    assert res.has_ee_dir
    assert set(res.ee_dirs) == {"ee", "packages/ee"}
    assert res.ee_license_excerpt.startswith("The Enterprise Edition")
    assert "ee_dir" in res.flags()


def test_copyleft_dependency(cfg, client):
    c = make_candidate(root_files=["README.md", "LICENSE", "package.json"])
    with _router() as r:
        gh = GitHubMock(r, c.full_name).license("MIT", MIT_TEXT).readme().package_json(
            {"ua-parser-js": "2.0.0", "lodash": "^4.17.21", "dual": "1.0.0", "ghost": "1.2.3"}
        )
        depsdev(r, "npm", "ua-parser-js", "2.0.0", ["AGPL-3.0-or-later"])
        depsdev(r, "npm", "lodash", "4.17.21", ["MIT"])
        depsdev(r, "npm", "dual", "1.0.0", ["GPL-3.0 OR MIT"])
        r.get(url__regex=r".*/packages/ghost.*").mock(return_value=httpx.Response(404, text="package not found"))
        res = _audit(client, cfg, gh, c)
    assert res.copyleft_deps == ["ua-parser-js (AGPL-3.0-or-later)"]
    assert res.unknown_deps == 1
    assert res.deps_checked == 4
    assert "copyleft_deps" in res.flags()


def test_dep_default_version_lookup(cfg, client):
    c = make_candidate(root_files=["README.md", "LICENSE", "package.json"])
    with _router() as r:
        gh = GitHubMock(r, c.full_name).license("MIT", MIT_TEXT).readme().package_json({"@scope/pkg": "latest"})
        depsdev_default(r, "npm", "@scope/pkg", "3.1.0", ["GPL-2.0"])
        res = _audit(client, cfg, gh, c)
    assert res.copyleft_deps == ["@scope/pkg (GPL-2.0)"]


def test_trademark_and_korea_signals(cfg, client):
    c = make_candidate(root_files=["README.md", "LICENSE"], root_dirs=["src", "locales"])
    readme = "# Widget\n\nWidget™ is a trademark. Payments via Stripe. Sign in with Google."
    with _router() as r:
        gh = GitHubMock(r, c.full_name).license("MIT", MIT_TEXT).readme(readme).contents("locales", [("en.json", "file"), ("ja.json", "file")])
        res = _audit(client, cfg, gh, c)
    assert res.trademark_notice
    assert res.signals.has_stripe and not res.signals.has_kr_pay
    assert res.signals.auth_mentioned and not res.signals.has_kr_login
    assert res.signals.korean_locale is False
    assert "locales" in res.signals.i18n_dirs_checked


def test_korean_locale_found_nested(cfg, client):
    c = make_candidate(root_files=["README.md", "LICENSE"], root_dirs=["src"])
    with _router() as r:
        gh = GitHubMock(r, c.full_name).license("MIT", MIT_TEXT).readme()
        gh.contents("src/i18n", [("locales", "dir"), ("index.ts", "file")])
        gh.contents("src/i18n/locales", [("en.json", "file"), ("ko-KR.json", "file")])
        res = _audit(client, cfg, gh, c)
    assert res.signals.korean_locale is True
    assert "src/i18n/locales" in res.signals.i18n_dirs_checked


def test_readme_weak_terms_are_soft_flags(cfg, client):
    c = make_candidate(root_files=["README.md", "LICENSE"])
    with _router() as r:
        gh = GitHubMock(r, c.full_name).license("MIT", MIT_TEXT).readme("# Widget\n\nMulti-tenant support built in. Enterprise Edition available.")
        res = _audit(client, cfg, gh, c)
    assert res.restricted_terms == []
    assert set(res.readme_terms) == {"multi-tenant", "enterprise edition"}
    assert "readme_terms" in res.flags() and "restricted_terms" not in res.flags()


# ---------------------------------------------------------------- unit helpers
def test_classify_text_families(cfg):
    assert classify_text(MIT_TEXT, cfg) == ("ok", "MIT")
    assert classify_text(AGPL_TEXT, cfg)[0] == "copyleft_or_restricted"
    assert classify_text("Business Source License 1.1", cfg)[0] == "copyleft_or_restricted"
    assert classify_text("some custom license nobody knows", cfg) == ("unknown", None)


def test_dep_is_copyleft(cfg):
    assert dep_is_copyleft(["GPL-3.0"], cfg)
    assert dep_is_copyleft(["AGPL-3.0-or-later"], cfg)
    assert not dep_is_copyleft(["LGPL-2.1"], cfg)  # LGPL is tolerated for deps per spec
    assert not dep_is_copyleft(["GPL-2.0 OR MIT"], cfg)
    assert not dep_is_copyleft(["Apache-2.0 OR MIT"], cfg)
    assert not dep_is_copyleft([], cfg)


def test_manifest_parsers():
    assert parse_package_json('{"dependencies": {"a": "^1.2.3", "b": "workspace:*", "c": "latest"}}') == [("a", "1.2.3"), ("c", None)]
    py = parse_pyproject('[project]\ndependencies = ["httpx>=0.27", "Django==5.0.1", "pkg[extra]"]\n')
    assert ("httpx", None) in py and ("django", "5.0.1") in py and ("pkg", None) in py
    assert parse_requirements("# c\nrequests==2.31.0\n-r other.txt\nflask\nhttps://x/y.whl\n") == [("requests", "2.31.0"), ("flask", None)]
    go = parse_go_mod("module x\n\nrequire (\n\tgithub.com/a/b v1.2.3\n\tgithub.com/c/d v0.1.0 // indirect\n)\nrequire github.com/e/f v2.0.0\n")
    assert go == [("github.com/a/b", "v1.2.3"), ("github.com/e/f", "v2.0.0")]
    cargo = parse_cargo_toml('[dependencies]\nserde = "1.0.200"\ntokio = { version = "1", features = ["full"] }\nlocal = { path = "../local" }\n')
    assert cargo == [("serde", "1.0.200"), ("tokio", None)]
