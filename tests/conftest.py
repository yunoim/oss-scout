"""Shared fixtures: config, offline GitHub client, respx helpers."""
from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from scout.config import load_config
from scout.discover import Candidate
from scout.github_client import API, DEPS_DEV, GitHubClient

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)

MIT_TEXT = """MIT License

Copyright (c) 2024 Example

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction...
"""

APACHE_PLUS_TEXT = """                                 Apache License
                           Version 2.0, January 2004

Additional Conditions

The software may not be used to provide a multi-tenant SaaS offering without
the express written permission of the licensor. You may not remove or obscure
the logo on the console.
"""

AGPL_TEXT = """                    GNU AFFERO GENERAL PUBLIC LICENSE
                       Version 3, 19 November 2007
"""

SUL_TEXT = """Sustainable Use License

Version 1.0

You may use or modify the software only for your own internal business purposes.
"""


@pytest.fixture(scope="session")
def cfg():
    return load_config()


@pytest.fixture
def client():
    c = GitHubClient(token="test-token", cache_path=None, sleep=lambda s: None)
    yield c
    c.http.close()


@pytest.fixture
def now():
    return NOW


def make_candidate(
    full_name: str = "acme/widget",
    stars: int = 5000,
    root_files: list[str] | None = None,
    root_dirs: list[str] | None = None,
    spdx: str | None = "MIT",
    topics: list[str] | None = None,
    description: str = "Self-hosted analytics dashboard",
    language: str = "TypeScript",
    contributors: int | None = 40,
    pushed_days_ago: int = 2,
    release_days_ago: int | None = 10,
    open_issues: int = 50,
) -> Candidate:
    return Candidate(
        full_name=full_name,
        html_url=f"https://github.com/{full_name}",
        description=description,
        language=language,
        stars=stars,
        forks=100,
        open_issues=open_issues,
        pushed_at=NOW - timedelta(days=pushed_days_ago),
        topics=topics if topics is not None else ["analytics", "self-hosted"],
        default_branch="main",
        license_spdx=spdx,
        root_files=root_files if root_files is not None else ["README.md", "LICENSE", "package.json", "Dockerfile", "docker-compose.yml", ".env.example"],
        root_dirs=root_dirs if root_dirs is not None else ["src"],
        has_readme=True,
        latest_release_at=(NOW - timedelta(days=release_days_ago)) if release_days_ago is not None else None,
        releases_fetched=True,
        contributors=contributors,
    )


def _b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


class GitHubMock:
    """Register the endpoints the auditor touches for one repo."""

    def __init__(self, router: respx.MockRouter, full_name: str):
        self.r = router
        self.base = f"{API}/repos/{full_name}"

    def license(self, spdx: str | None, text: str | None, status: int = 200):
        if status != 200 or text is None:
            self.r.get(f"{self.base}/license").mock(return_value=httpx.Response(404, json={"message": "Not Found"}))
            return self
        body = {"license": {"spdx_id": spdx or "NOASSERTION"}, "content": _b64(text), "encoding": "base64"}
        self.r.get(f"{self.base}/license").mock(return_value=httpx.Response(200, json=body))
        return self

    def readme(self, text: str | None = "# Widget\n\nA self-hosted analytics tool. Login with OAuth."):
        if text is None:
            self.r.get(f"{self.base}/readme").mock(return_value=httpx.Response(404, json={}))
        else:
            self.r.get(f"{self.base}/readme").mock(return_value=httpx.Response(200, text=text, headers={"content-type": "text/plain"}))
        return self

    def contents(self, path: str, entries: list[tuple[str, str]] | None):
        url = f"{self.base}/contents/{path}"
        if entries is None:
            self.r.get(url).mock(return_value=httpx.Response(404, json={"message": "Not Found"}))
        else:
            self.r.get(url).mock(
                return_value=httpx.Response(200, json=[{"name": n, "type": t, "path": f"{path}/{n}".strip("/")} for n, t in entries])
            )
        return self

    def file(self, path: str, text: str):
        self.r.get(f"{self.base}/contents/{path}").mock(return_value=httpx.Response(200, text=text, headers={"content-type": "text/plain"}))
        return self

    def package_json(self, deps: dict[str, str]):
        return self.file("package.json", json.dumps({"name": "widget", "dependencies": deps}))

    def fallback(self):
        """Any other contents path (e.g. i18n probes) -> 404. Register last: respx matches in order."""
        import re

        self.r.get(url__regex=rf"{re.escape(self.base)}/contents/.*").mock(return_value=httpx.Response(404, json={"message": "Not Found"}))
        return self


def depsdev(router: respx.MockRouter, system: str, name: str, version: str, licenses: list[str]):
    from urllib.parse import quote

    url = f"{DEPS_DEV}/systems/{system}/packages/{quote(name, safe='')}/versions/{quote(version, safe='')}"
    router.get(url).mock(return_value=httpx.Response(200, json={"versionKey": {"name": name, "version": version}, "licenses": licenses}))


def depsdev_default(router: respx.MockRouter, system: str, name: str, version: str, licenses: list[str]):
    from urllib.parse import quote

    base = f"{DEPS_DEV}/systems/{system}/packages/{quote(name, safe='')}"
    router.get(base).mock(return_value=httpx.Response(200, json={"versions": [{"versionKey": {"version": version}, "isDefault": True}]}))
    depsdev(router, system, name, version, licenses)
