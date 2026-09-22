from __future__ import annotations

import httpx
import pytest
import respx

from scout.market import NAVER_API, NAVER_APIHUB, MarketSignals, NaverSearch, awareness_points, buyer_breadth, collect_market
from scout.score import score_candidate
from tests.conftest import NOW, make_candidate
from tests.test_score import _ok_audit


def test_breadth_rules(cfg):
    assert buyer_breadth(make_candidate(topics=["newsletter", "cms"], description="Publishing platform"), "cms", cfg)[0] == "narrow"
    assert buyer_breadth(make_candidate(topics=["homelab", "monitoring"]), "monitoring", cfg)[0] == "narrow"
    assert buyer_breadth(make_candidate(topics=["homelab", "kubernetes", "proxmox"]), "monitoring", cfg)[0] == "narrow"  # narrow beats infra
    assert buyer_breadth(make_candidate(topics=["analytics", "self-hosted"]), "analytics", cfg)[0] == "business"
    assert buyer_breadth(make_candidate(topics=["observability", "monitoring"]), "monitoring", cfg)[0] == "enterprise"
    assert buyer_breadth(make_candidate(topics=["cli"]), "devtool", cfg)[0] == "devtool"
    assert buyer_breadth(make_candidate(topics=["chat", "messenger"]), "other", cfg)[0] == "consumer"
    assert buyer_breadth(make_candidate(topics=["database", "library"]), "lib", cfg)[0] == "devtool"  # libs never enterprise


def test_framework_vs_product(cfg):
    from scout.market import looks_like_framework

    lib = make_candidate(topics=["llm", "rag"], root_files=["README.md", "pyproject.toml", "LICENSE"], root_dirs=["src", "tests", "docs"])
    app = make_candidate(topics=["llm", "rag"], root_files=["README.md", "pyproject.toml", "Dockerfile", "docker-compose.yml"], root_dirs=["src", "webui"])
    ui_only = make_candidate(topics=["llm"], root_files=["README.md", "package.json"], root_dirs=["frontend", "backend"])
    no_manifest = make_candidate(topics=["llm"], root_files=["README.md"], root_dirs=["scripts"])
    assert looks_like_framework(lib)
    assert not looks_like_framework(app)
    assert not looks_like_framework(ui_only)
    assert not looks_like_framework(no_manifest)
    assert buyer_breadth(lib, "llm-workflow", cfg) == ("devtool", "package without Dockerfile/compose/UI (framework, not a product)")
    assert buyer_breadth(app, "llm-workflow", cfg)[0] == "business"


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
    assert any("market narrow" in n for n in s_narrow.notes)
    mc = cfg.scoring.market
    if mc.awareness_points == 0:
        # awareness disabled (2026-W39 calibration): market is breadth only, no unknown flag
        assert "market" not in s_narrow.unknowns
        assert s_biz.components["market"] == pytest.approx(cfg.scoring.weights["market"] * 5 / mc.breadth_max, abs=0.01)
        m = MarketSignals(breadth="business", breadth_reason="x", naver_total=5000)
        assert score_candidate(biz, a, cfg, now=NOW, market=m).components["market"] == s_biz.components["market"]
        assert score_candidate(biz, a, cfg, now=NOW, market=m).naver_mentions == 5000  # still recorded
    else:
        assert "market" in s_narrow.unknowns
        m = MarketSignals(breadth="business", breadth_reason="x", naver_total=10**9)
        s_known = score_candidate(biz, a, cfg, now=NOW, market=m)
        assert "market" not in s_known.unknowns
        assert s_known.components["market"] == cfg.scoring.weights["market"] * (5 + mc.awareness_points) / (mc.breadth_max + mc.awareness_points)


def test_naver_collect_apihub(cfg):
    c = make_candidate(full_name="acme/widget", topics=["analytics"])
    with respx.mock() as r:
        r.get(f"{NAVER_APIHUB}/blog").mock(return_value=httpx.Response(200, json={"total": 120}))
        r.get(f"{NAVER_APIHUB}/cafearticle").mock(return_value=httpx.Response(200, json={"total": 30}))
        r.get(f"{NAVER_APIHUB}/news").mock(return_value=httpx.Response(401, json={"errorMessage": "bad key"}))
        naver = NaverSearch("kid", "ksecret")  # default mode = apihub
        sig = collect_market(c, "analytics", cfg, naver)
        naver.close()
        first = r.calls[0].request
    assert sig.breadth == "business"
    assert sig.naver_blog == 120 and sig.naver_cafe == 30 and sig.naver_news is None
    assert sig.naver_total == 150
    assert first.headers["X-NCP-APIGW-API-KEY-ID"] == "kid" and first.headers["X-NCP-APIGW-API-KEY"] == "ksecret"
    assert str(first.url).count("widget") == 1 and "github" in str(first.url)


def test_awareness_query_normalises_name():
    from scout.market import awareness_query

    assert awareness_query(make_candidate(full_name="louislam/uptime-kuma")) == "uptime kuma github"
    assert awareness_query(make_candidate(full_name="a/daily_stock_analysis")) == "daily stock analysis github"


def test_naver_collect_legacy(cfg):
    c = make_candidate(full_name="acme/widget", topics=["analytics"])
    with respx.mock() as r:
        for k in ("blog", "cafearticle", "news"):
            r.get(f"{NAVER_API}/{k}.json").mock(return_value=httpx.Response(200, json={"total": 10}))
        naver = NaverSearch("id", "secret", mode="legacy")
        sig = collect_market(c, "analytics", cfg, naver)
        naver.close()
        first = r.calls[0].request
    assert sig.naver_total == 30
    assert first.headers["X-Naver-Client-Id"] == "id"


def test_env_naver_mode(monkeypatch):
    from scout.config import load_env

    for k in ("NCP_APIGW_KEY_ID", "NCP_APIGW_KEY", "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET"):
        monkeypatch.delenv(k, raising=False)
    assert load_env(dotenv_path="nonexistent.env").naver_mode is None
    monkeypatch.setenv("NAVER_CLIENT_ID", "a"); monkeypatch.setenv("NAVER_CLIENT_SECRET", "b")
    assert load_env(dotenv_path="nonexistent.env").naver_mode == "legacy"
    monkeypatch.setenv("NCP_APIGW_KEY_ID", "c"); monkeypatch.setenv("NCP_APIGW_KEY", "d")
    assert load_env(dotenv_path="nonexistent.env").naver_mode == "apihub"  # API HUB wins when both exist
