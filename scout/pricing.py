"""Pricing-page signal (CEO-157, 2026-10-05): does someone already sell this at a small-business price?

v1 is display only (report card + Notion Notes); it does not touch the score until 2 weeks of observation.
Design: docs/design/pricing-signal.md.

Network rules are fixed in code, not config (CEO condition):
- identifying User-Agent, no retries, at most MAX_PAGE_REQUESTS page GETs per repo (a page may follow up to
  MAX_REDIRECTS redirect hops; each hop is checked against robots.txt before it is requested)
- public hosts only: every hop must be http(s) on port 80/443 and resolve to public IPs (no loopback, private,
  link-local or reserved — the homepage URL comes from arbitrary GitHub repo metadata and this runs on Actions)
- bodies are streamed and cut at MAX_BYTES
- robots.txt is honoured: a disallowed path -> tier `unknown`. robots.txt itself is fetched once per host per run
  (cached across repos) and is not counted as a page request.
"""
from __future__ import annotations

import html as htmllib
import ipaddress
import socket
import logging
import re
from typing import Literal
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from pydantic import BaseModel

from .config import Config

log = logging.getLogger(__name__)

USER_AGENT = "oss-scout/1.0 (+https://github.com/yunoim/oss-scout; weekly pricing check)"
MAX_PAGE_REQUESTS = 2   # homepage + one pricing page
MAX_REDIRECTS = 3       # per page; every hop is robots-checked before it is requested
TIMEOUT_S = 10.0
MAX_BYTES = 2_000_000    # stop reading a body after this (pages and robots.txt)
MIN_TEXT_CHARS = 600    # less visible text than this = JS-rendered shell (SPA) -> unreadable

Tier = Literal["selfserve", "pricey", "sales", "no_price", "unknown"]

# currency symbol, amount, then a period/unit: "$9.99/mo", "€10 / month", "$5 per user", "₩9,900/월"
PRICE_RE = re.compile(
    r"(?P<cur>[$€£₩])\s?(?P<amt>\d{1,3}(?:[,.]\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)\s*"
    r"(?:/|per\s+|a\s+)\s*(?P<unit>mo\b|month|월|user|seat|member|yr\b|year|annum|년)",
    re.I,
)
SALES_RE = re.compile(r"contact\s+sales|talk\s+to\s+sales|book\s+a\s+demo|request\s+a\s+(?:quote|demo)|schedule\s+a\s+demo", re.I)
PRICING_HREF_RE = re.compile(r"""href\s*=\s*["']([^"']*pric[^"']*)["']""", re.I)
# multi-label public suffixes we meet in practice (a full PSL is overkill for this)
TWO_LABEL_SUFFIXES = {"co.uk", "co.kr", "or.kr", "co.jp", "com.au", "com.br", "com.cn", "github.io", "gitlab.io",
                      "vercel.app", "netlify.app", "pages.dev", "herokuapp.com", "readthedocs.io"}


class PricingSignal(BaseModel):
    full_name: str
    tier: Tier = "unknown"
    min_usd_month: float | None = None
    source_url: str | None = None   # page the price (or sales wording) was found on
    note: str = ""
    requests: int = 0               # page GETs made (<= MAX_PAGE_REQUESTS)

    def label(self) -> str:
        price = f" · 최저 ${self.min_usd_month:g}/월" if self.min_usd_month is not None else ""
        src = f" · {self.source_url}" if self.source_url else ""
        why = f" ({self.note})" if self.note and self.tier == "unknown" else ""
        return f"{self.tier}{price}{src}{why}"


# ------------------------------------------------------------------ parsing (pure)
def visible_text(html: str) -> str:
    """Text a visitor sees: drop script/style/noscript/template blocks, tags and entities."""
    t = re.sub(r"<(script|style|noscript|template)\b.*?</\1\s*>", " ", html, flags=re.S | re.I)
    t = re.sub(r"<!--.*?-->", " ", t, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", htmllib.unescape(t)).strip()


def _amount(raw: str) -> float:
    s = raw.replace(",", "")
    if s.count(".") > 1 or re.fullmatch(r"\d{1,3}\.\d{3}", s):  # "1.000" thousands separator (EU)
        s = s.replace(".", "")
    return float(s)


def prices_usd_month(text: str, fx: dict[str, float]) -> list[float]:
    out = []
    for m in PRICE_RE.finditer(text):
        usd = _amount(m.group("amt")) * fx.get(m.group("cur"), 1.0)
        if m.group("unit").lower() in ("yr", "year", "annum", "년"):
            usd /= 12
        out.append(round(usd, 2))
    return out


def registrable_domain(host: str) -> str:
    labels = (host or "").lower().rstrip(".").split(".")
    if len(labels) >= 3 and ".".join(labels[-2:]) in TWO_LABEL_SUFFIXES:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def pricing_link(html: str, base_url: str) -> str | None:
    """First href containing 'pric' on the same registrable domain as the (final, post-redirect) homepage."""
    base_dom = registrable_domain(urlparse(base_url).hostname or "")
    for href in PRICING_HREF_RE.findall(html):
        url = urljoin(base_url, htmllib.unescape(href.strip()))
        p = urlparse(url)
        if p.scheme not in ("http", "https"):
            continue
        if registrable_domain(p.hostname or "") != base_dom:
            continue
        if urlparse(base_url)._replace(fragment="").geturl() == p._replace(fragment="").geturl():
            continue  # "/#pricing" on the page we already have
        return p._replace(fragment="").geturl()
    return None


def classify(home_text: str | None, pricing_text: str | None, category: str, cfg: Config,
             home_url: str | None = None, pricing_url: str | None = None) -> tuple[Tier, float | None, str | None, str]:
    """-> (tier, min_usd_month, source_url, note). Pure: no network."""
    pc = cfg.pricing
    readable_home = home_text if home_text and len(home_text) >= MIN_TEXT_CHARS else None
    readable_pricing = pricing_text if pricing_text and len(pricing_text) >= MIN_TEXT_CHARS // 3 else None
    if readable_home is None and readable_pricing is None:
        return "unknown", None, None, "본문 없음(JS 렌더링 추정)" if home_text is not None else "페이지 못 읽음"

    found: list[tuple[float, str | None]] = []
    if readable_pricing:
        found += [(p, pricing_url) for p in prices_usd_month(readable_pricing, pc.fx)]
    # a shop/hosting product shows *its demo store's* prices on the homepage (Paymenter $5/mo) -> only trust a pricing page
    if readable_home and category not in pc.home_price_ignored_categories:
        found += [(p, home_url) for p in prices_usd_month(readable_home, pc.fx)]
    if found:
        low, src = min(found, key=lambda x: x[0])
        return ("selfserve" if low <= pc.selfserve_max_usd else "pricey"), low, src, ""
    for t, u in ((readable_pricing, pricing_url), (readable_home, home_url)):
        if t and SALES_RE.search(t):
            return "sales", None, u, ""
    return "no_price", None, None, ""


# ------------------------------------------------------------------ network
class Blocked(Exception):
    """URL refused before any request (non-public host, odd scheme/port)."""


def check_public_url(url: str) -> None:
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise Blocked("http(s) 아님")
    if p.port not in (None, 80, 443):
        raise Blocked(f"포트 {p.port}")
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise Blocked("DNS 실패") from None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_multicast:
            raise Blocked("공개 주소 아님")


class PricingFetcher:
    """One per run. Holds the HTTP client and the per-host robots.txt cache."""

    def __init__(self, transport: httpx.BaseTransport | None = None, check_url=check_public_url):
        # transport retries stay at httpx's default of 0; no tenacity here on purpose (CEO condition: no retries)
        self.client = httpx.Client(timeout=TIMEOUT_S, follow_redirects=False, transport=transport,
                                   headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
        self._robots: dict[str, RobotFileParser | None] = {}
        self._check_url = check_url  # tests inject a no-op (MockTransport hosts don't resolve)

    def _get(self, url: str) -> tuple[httpx.Response, str]:
        """One GET of a vetted public URL; body streamed and cut at MAX_BYTES. Returns (response, text)."""
        self._check_url(url)
        with self.client.stream("GET", url) as r:
            buf = bytearray()
            for chunk in r.iter_bytes():
                buf += chunk
                if len(buf) >= MAX_BYTES:
                    break
            text = bytes(buf[:MAX_BYTES]).decode(r.encoding or "utf-8", errors="replace")
        return r, text

    def close(self) -> None:
        self.client.close()

    def _robots_allows(self, url: str) -> bool | None:
        """True/False per robots.txt; None when robots.txt itself could not be read (server error / network)."""
        p = urlparse(url)
        host = f"{p.scheme}://{p.netloc}"
        if host not in self._robots:
            rp: RobotFileParser | None = RobotFileParser()
            try:
                r, body = self._get(f"{host}/robots.txt")
                if r.status_code in (401, 403):
                    rp.disallow_all = True  # type: ignore[union-attr]
                elif r.status_code >= 500:
                    rp = None
                elif r.status_code >= 400:
                    rp.allow_all = True  # type: ignore[union-attr]
                else:
                    rp.parse(body.splitlines())  # type: ignore[union-attr]
            except (httpx.HTTPError, Blocked):
                rp = None
            self._robots[host] = rp
        rp = self._robots[host]
        return None if rp is None else rp.can_fetch(USER_AGENT, url)

    def fetch(self, full_name: str, homepage: str | None, category: str, cfg: Config) -> PricingSignal:
        sig = PricingSignal(full_name=full_name)
        if not homepage or not homepage.startswith(("http://", "https://")):
            sig.note = "homepage 없음"
            return sig

        def get(url: str) -> tuple[httpx.Response, str] | None:
            if sig.requests >= MAX_PAGE_REQUESTS:
                raise RuntimeError("page request cap reached")  # guards future edits; never hit by the flow below
            counted = False
            for _ in range(MAX_REDIRECTS + 1):
                allowed = self._robots_allows(url)
                if allowed is not True:
                    sig.note = "robots.txt 차단" if allowed is False else "robots.txt 못 읽음"
                    return None
                try:
                    self._check_url(url)  # refuse non-public hosts before counting or requesting anything
                except Blocked as e:
                    sig.note = f"차단: {e}"
                    return None
                if not counted:  # a page counts once, when its first hop is actually requested
                    sig.requests += 1
                    counted = True
                try:
                    r, body = self._get(url)
                except Blocked as e:
                    sig.note = f"차단: {e}"
                    return None
                except httpx.HTTPError as e:
                    sig.note = f"요청 실패: {type(e).__name__}"
                    return None
                if r.is_redirect and r.headers.get("location"):
                    url = urljoin(str(r.url), r.headers["location"])
                    if not url.startswith(("http://", "https://")):
                        sig.note = "이상한 리다이렉트"
                        return None
                    continue
                if r.status_code >= 400 or "html" not in r.headers.get("content-type", "html"):
                    sig.note = f"HTTP {r.status_code}"
                    return None
                return r, body
            sig.note = "리다이렉트 너무 많음"
            return None

        home = get(homepage)
        if home is None:
            return sig
        home_r, home_html = home
        home_url = str(home_r.url)
        plink = pricing_link(home_html, home_url)
        pricing_text = pricing_url = None
        if plink:
            pr = get(plink)
            if pr is not None:
                pricing_text, pricing_url = visible_text(pr[1]), str(pr[0].url)
        tier, low, src, note = classify(visible_text(home_html), pricing_text, category, cfg, home_url, pricing_url)
        sig.tier, sig.min_usd_month, sig.source_url = tier, low, src
        sig.note = note or (sig.note if tier == "unknown" else "")
        return sig
