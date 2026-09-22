from __future__ import annotations

import httpx
import respx

from scout.market import NAVER_API, MarketSignals, NaverSearch, awareness_points, buyer_breadth, collect_market
from scout.score import score_candidate
from tests.conftest import NOW, make_candidate
from tests.test_score import _ok_audit


def test_breadth_rules(cfg):
    assert buyer_breadth(make_candidate(topics=["newsletter", "cms"], description="Publishing platform"), "cms", cfg)[0] == "narrow"
    assert buyer_breadth(make_candidate(topics=["homelab", "monitoring"]), "monitoring", cfg)[0] == "narrow"
    assert buyer_breadth(make_candidate(topics=["analytics", "self-hosted"]), "analytics", cfg)[0] == "business"
    assert buyer_breadth(make_candidate(topics=["observability", "monitoring"]), "monitoring", cfg)[0] == "enterprise"
    assert buyer_breadth(make_candidate(topics=["cli"]), "devtool", cfg)[0] == "devtool"
    assert buyer_breadth(make_candidate(topics=["chat", "messenger"]), "other", cfg)[0] == "consumer"
    assert buyer_breadth(make_candidate(topics=["database", "library"]), "lib", cfg)[0] == "devtool"  # libs never enterprise


def test_awareness_points():
    assert awareness_points(None, 4, 3000) is None
    assert awareness_points(0, 4, 3000) == 0.0
    assert awareness_points(3000, 4, 3000) == 4.0
    assert 0 < awareness_points(30, 4, 3000) < 2.5


def test_market_component_moves_score(cfg):
    a = _ok_audit()
    ghost_like = make_candidate(full_name="pub/letter", stars=50_000, topics=["cms", "newsletter", "blog"], description="Publishing platform")
    biz = make_candidate(full_name="biz/analytics", stars=50_000, topics=["analytics", "self-hosted"], description="Web analytics")
    s_narrow = score_candidate(ghost_like, a, cfg, now=NOW)
    s_biz = score_candidate(biz, a, cfg, now=NOW)
    assert s_narrow.breadth == "narrow" and s_biz.breadth == "business"
    assert s_narrow.components["market"] < s_biz.components["market"]
    assert "market" in s_narrow.unknowns  # no Naver -> awareness unknown
    assert any("market narrow" in n for n in s_narrow.notes)
    # with Naver evidence the unknown disappears and full awareness lifts the score
    m = MarketSignals(breadth="business", breadth_reason="x", naver_total=5000)
    s_known = score_candidate(biz, a, cfg, now=NOW, market=m)
    assert "market" not in s_known.unknowns
    assert s_known.components["market"] == cfg.scoring.weights["market"] * (5 + 4) / (6 + 4)


def test_naver_collect(cfg):
    c = make_candidate(full_name="acme/widget", topics=["analytics"])
    with respx.mock() as r:
        r.get(f"{NAVER_API}/blog.json").mock(return_value=httpx.Response(200, json={"total": 120}))
        r.get(f"{NAVER_API}/cafearticle.json").mock(return_value=httpx.Response(200, json={"total": 30}))
        r.get(f"{NAVER_API}/news.json").mock(return_value=httpx.Response(401, json={"errorMessage": "bad key"}))
        naver = NaverSearch("id", "secret")
        sig = collect_market(c, "analytics", cfg, naver)
        naver.close()
        first_url = str(r.calls[0].request.url)
    assert sig.breadth == "business"
    assert sig.naver_blog == 120 and sig.naver_cafe == 30 and sig.naver_news is None
    assert sig.naver_total == 150
    assert first_url.count("widget") == 1 and "%EC%98%A4%ED%94%88%EC%86%8C%EC%8A%A4" in first_url  # "오픈소스"
