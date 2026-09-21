from __future__ import annotations

import httpx
import respx

from scout.discover import discover, prefilter_reason, render_queries
from scout.github_client import API, GitHubClient
from tests.conftest import NOW, make_candidate


def test_etag_cache_returns_cached_body_on_304(tmp_path):
    cache = tmp_path / "etag.json"
    with respx.mock(assert_all_called=True) as r:
        route = r.get(f"{API}/repos/a/b").mock(
            side_effect=[
                httpx.Response(200, json={"full_name": "a/b", "stargazers_count": 1}, headers={"etag": 'W/"abc"'}),
                httpx.Response(304, headers={"etag": 'W/"abc"'}),
            ]
        )
        c1 = GitHubClient("t", cache_path=cache, sleep=lambda s: None)
        assert c1.repo("a/b")["stargazers_count"] == 1
        c1.close()
        assert cache.exists()

        c2 = GitHubClient("t", cache_path=cache, sleep=lambda s: None)
        body = c2.repo("a/b")
        assert body == {"full_name": "a/b", "stargazers_count": 1}
        assert c2.cache.hits == 1
        assert route.calls[1].request.headers["if-none-match"] == 'W/"abc"'
        c2.close()


def test_rate_limit_sleep_until_reset():
    slept: list[float] = []
    with respx.mock() as r:
        r.get(f"{API}/repos/a/b").mock(
            return_value=httpx.Response(200, json={}, headers={"x-ratelimit-remaining": "2", "x-ratelimit-reset": "9999999999"})
        )
        c = GitHubClient("t", sleep=slept.append)
        c.repo("a/b")
    assert slept and slept[0] > 1000


def test_secondary_rate_limit_retries():
    slept: list[float] = []
    with respx.mock() as r:
        r.get(f"{API}/repos/a/b").mock(
            side_effect=[
                httpx.Response(403, text="API rate limit exceeded", headers={"retry-after": "7"}),
                httpx.Response(200, json={"ok": True}),
            ]
        )
        c = GitHubClient("t", sleep=slept.append)
        assert c.repo("a/b") == {"ok": True}
    assert 7 in slept


def test_contributors_count_from_link_header():
    with respx.mock() as r:
        r.get(f"{API}/repos/a/b/contributors").mock(
            return_value=httpx.Response(
                200, json=[{"login": "x"}],
                headers={"link": '<https://api.github.com/repositories/1/contributors?per_page=1&anon=true&page=2>; rel="next", '
                                 '<https://api.github.com/repositories/1/contributors?per_page=1&anon=true&page=437>; rel="last"'},
            )
        )
        r.get(f"{API}/repos/a/solo/contributors").mock(return_value=httpx.Response(200, json=[{"login": "x"}]))
        r.get(f"{API}/repos/a/empty/contributors").mock(return_value=httpx.Response(204))
        c = GitHubClient("t", sleep=lambda s: None)
        assert c.contributors_count("a/b") == 437
        assert c.contributors_count("a/solo") == 1
        assert c.contributors_count("a/empty") == 0


def test_render_queries_substitutes_dates(cfg):
    qs = render_queries(cfg, NOW)
    assert all("{90d}" not in q for q in qs)
    assert "pushed:>2026-06-23" in qs[0]


def test_prefilter(cfg):
    assert prefilter_reason(make_candidate(), cfg, NOW) is None
    assert prefilter_reason(make_candidate(topics=["awesome", "cms"]), cfg, NOW) == "non-product topic: awesome"
    assert prefilter_reason(make_candidate(full_name="x/awesome-selfhosted"), cfg, NOW).startswith("name pattern")
    assert prefilter_reason(make_candidate(pushed_days_ago=120), cfg, NOW).startswith("stale")
    c = make_candidate()
    c.archived = True
    assert prefilter_reason(c, cfg, NOW) == "archived"


def test_discover_end_to_end(cfg):
    item = {"full_name": "acme/widget", "html_url": "https://github.com/acme/widget", "stargazers_count": 900, "forks_count": 1,
            "open_issues_count": 3, "pushed_at": "2026-09-20T00:00:00Z", "archived": False, "fork": False, "topics": ["analytics"],
            "default_branch": "main", "license": {"spdx_id": "MIT"}, "description": "d", "language": "Go"}
    noise = dict(item, full_name="x/awesome-list", html_url="https://github.com/x/awesome-list", topics=["awesome"])
    with respx.mock(assert_all_called=False) as r:
        r.get(f"{API}/search/repositories").mock(return_value=httpx.Response(200, json={"total_count": 2, "items": [item, noise]}))
        r.get(f"{API}/repos/acme/widget").mock(return_value=httpx.Response(200, json=item))
        r.get(f"{API}/repos/acme/widget/contents/").mock(return_value=httpx.Response(200, json=[{"name": "README.md", "type": "file"}, {"name": "Dockerfile", "type": "file"}, {"name": "src", "type": "dir"}]))
        r.get(f"{API}/repos/acme/widget/releases").mock(return_value=httpx.Response(200, json=[{"tag_name": "v1", "published_at": "2026-09-01T00:00:00Z", "draft": False}]))
        r.get(f"{API}/repos/acme/widget/contributors").mock(return_value=httpx.Response(200, json=[{"login": "a"}]))
        client = GitHubClient("t", sleep=lambda s: None)
        cands, dropped, raw = discover(client, cfg, now=NOW)
    assert raw == 2
    assert [c.full_name for c in cands] == ["acme/widget"]
    assert "x/awesome-list" in dropped
    c = cands[0]
    assert c.root_files == ["README.md", "Dockerfile"] and c.root_dirs == ["src"]
    assert c.latest_release_at.year == 2026 and c.releases_fetched
    assert c.contributors == 1
    assert len(c.matched_queries) == len(cfg.discovery.queries)
