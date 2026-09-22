from __future__ import annotations

import httpx
import respx

from scout.demand import build_query, fetch_signals
from scout.github_client import API
from tests.conftest import NOW


def _item(title, number, is_pr=False, state="open", created="2026-08-01T00:00:00Z", plus1=0):
    d = {
        "title": title,
        "html_url": f"https://github.com/acme/widget/{'pull' if is_pr else 'issues'}/{number}",
        "state": state,
        "created_at": created,
        "reactions": {"+1": plus1, "total_count": plus1},
    }
    if is_pr:
        d["pull_request"] = {"url": "x"}
    return d


def test_build_query_groups_keywords(cfg):
    q = build_query("acme/widget", cfg)
    assert q.startswith("repo:acme/widget AND (")
    assert " OR " in q and "한국어 in:title" in q and q.endswith(")")
    assert q.count("in:title") == len(cfg.demand.keywords)


def test_fetch_signals_counts(cfg, client):
    items = [
        _item("Korean translation?", 1, plus1=5),
        _item("Add ko locale", 2, is_pr=True, state="closed", created="2016-03-01T00:00:00Z"),
        _item("KakaoPay support", 3, state="closed", created="2026-01-15T00:00:00Z", plus1=2),
        _item("Naver login", 4, state="open", created="2024-01-01T00:00:00Z"),
    ]
    with respx.mock() as r:
        route = r.get(f"{API}/search/issues").mock(return_value=httpx.Response(200, json={"total_count": 4, "items": items}))
        sig = fetch_signals(client, "acme/widget", cfg, now=NOW)
    assert route.called
    assert "advanced_search" in str(route.calls[0].request.url)
    assert sig.fetched and sig.total == 4
    assert sig.issues == 3 and sig.prs == 1
    assert sig.open_issues == 2
    assert sig.recent == 2  # 2026-08 and 2026-01 within 365d of NOW (2026-09-21)
    assert sig.reactions == 7
    assert sig.latest_at.year == 2026 and sig.latest_at.month == 8
    assert len(sig.top) == cfg.demand.top_issues
    assert sig.top[0].title == "Korean translation?"  # open + most reactions first
    assert sig.score > 0


def test_fetch_signals_failure_is_soft(cfg, client):
    with respx.mock() as r:
        r.get(f"{API}/search/issues").mock(return_value=httpx.Response(422, json={"message": "Validation Failed"}))
        sig = fetch_signals(client, "acme/widget", cfg, now=NOW)
    assert not sig.fetched and sig.total == 0 and sig.top == []


def test_report_demand_section(cfg):
    from scout.demand import DemandSignals, SignalIssue
    from scout.report import Entry, RunSummary, build_report
    from tests.conftest import make_candidate
    from scout.audit import AuditResult, Signals
    from scout.score import score_candidate

    c = make_candidate(full_name="acme/hot", stars=5000)
    a = AuditResult(full_name=c.full_name, license_status="ok", spdx="MIT", readme_fetched=True, signals=Signals(korean_locale=False))
    e = Entry(c, a, score_candidate(c, a, cfg, now=NOW))
    e.demand = DemandSignals(full_name=c.full_name, fetched=True, total=3, issues=2, prs=1, open_issues=1, recent=1, reactions=4,
                             top=[SignalIssue(title='Korean "ko" locale?', url="https://github.com/acme/hot/issues/7", state="open", is_pr=False)])
    quiet = make_candidate(full_name="acme/quiet", stars=4000)
    e2 = Entry(quiet, AuditResult(full_name=quiet.full_name, license_status="ok", spdx="MIT"), score_candidate(quiet, a, cfg, now=NOW))
    e2.demand = DemandSignals(full_name=quiet.full_name, fetched=True)
    md = build_report(RunSummary(week="2026-W39", generated_at=NOW, searched=2, prefiltered={}, entries=[e, e2]), cfg)
    assert "## 한국 수요 신호 Top 10" in md
    assert "| [acme/hot](https://github.com/acme/hot) |" in md.split("## 한국 수요 신호")[1]
    assert "acme/quiet" not in md.split("## 한국 수요 신호")[1].split("## 제외 목록")[0]
    assert "2i/1p (1 open)" in md  # table column
    assert "https://github.com/acme/hot/issues/7" in md
    assert '"Korean \'ko\' locale?"' in md  # quotes sanitised inside the markdown link title
