"""Market breadth: who buys this in Korea, and how many of them exist.

Two parts:
- buyer breadth (rule based, no API): individuals/creators < developers < every business < enterprise infra
- Korean awareness (optional Naver Search API): blog + cafe + news mention counts, log-scaled
"""
from __future__ import annotations

import logging
import math
import re
from typing import Literal

import httpx
from pydantic import BaseModel

from .config import Config
from .discover import Candidate

log = logging.getLogger(__name__)

Breadth = Literal["narrow", "consumer", "devtool", "business", "enterprise"]

NAVER_API = "https://openapi.naver.com/v1/search"


class MarketSignals(BaseModel):
    breadth: Breadth = "business"
    breadth_reason: str = ""
    naver_total: int | None = None  # None = not queried / failed
    naver_blog: int | None = None
    naver_cafe: int | None = None
    naver_news: int | None = None


def buyer_breadth(c: Candidate, category: str, cfg: Config) -> tuple[Breadth, str]:
    m = cfg.scoring.market
    topics = set(c.topics)
    text = f"{c.name} {(c.description or '')}".lower()
    tokens = set(re.split(r"[^a-z0-9]+", text))

    def hit(words: list[str]) -> str | None:
        for w in words:
            wl = w.lower()
            if wl in topics or wl in tokens or (" " in wl and wl in text):
                return w
        return None

    if (w := hit(m.enterprise_topics)) and category not in ("lib",):
        return "enterprise", f"enterprise topic: {w}"
    if (w := hit(m.narrow_topics)):
        return "narrow", f"individual/creator topic: {w}"
    if (w := hit(m.consumer_topics)):
        return "consumer", f"consumer topic: {w}"
    if category in ("devtool", "lib"):
        return "devtool", f"category {category}"
    if category in m.business_categories:
        return "business", f"category {category}"
    return "consumer", "no business category matched"


class NaverSearch:
    """Naver Search API counts. Free tier: 25,000 calls/day."""

    def __init__(self, client_id: str, client_secret: str, timeout: float = 15.0):
        self.http = httpx.Client(
            headers={"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret, "User-Agent": "oss-scout/0.1"},
            timeout=timeout,
        )

    def total(self, kind: str, query: str) -> int | None:
        try:
            r = self.http.get(f"{NAVER_API}/{kind}.json", params={"query": query, "display": 1})
        except httpx.HTTPError as e:
            log.debug("naver %s failed: %s", kind, e)
            return None
        if r.status_code != 200:
            log.debug("naver %s HTTP %s: %s", kind, r.status_code, r.text[:120])
            return None
        try:
            return int(r.json().get("total") or 0)
        except (ValueError, AttributeError):
            return None

    def close(self) -> None:
        self.http.close()


def awareness_query(c: Candidate) -> str:
    """Repo name plus a disambiguator so common words (docs, hive, pulse) don't count everything."""
    return f'"{c.name}" 오픈소스'


def collect_market(c: Candidate, category: str, cfg: Config, naver: NaverSearch | None) -> MarketSignals:
    breadth, reason = buyer_breadth(c, category, cfg)
    sig = MarketSignals(breadth=breadth, breadth_reason=reason)
    if naver is not None:
        q = awareness_query(c)
        sig.naver_blog = naver.total("blog", q)
        sig.naver_cafe = naver.total("cafearticle", q)
        sig.naver_news = naver.total("news", q)
        parts = [x for x in (sig.naver_blog, sig.naver_cafe, sig.naver_news) if x is not None]
        sig.naver_total = sum(parts) if parts else None
    return sig


def awareness_points(total: int | None, max_points: int, full_at: int) -> float | None:
    """log10 scale: 0 mentions -> 0, `full_at` mentions -> max. None if unknown."""
    if total is None:
        return None
    if total <= 0:
        return 0.0
    return round(min(math.log10(total + 1) / math.log10(full_at + 1), 1.0) * max_points, 2)
