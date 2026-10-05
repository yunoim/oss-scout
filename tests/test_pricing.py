"""CEO-157 pricing signal — the 10 design cases (docs/design/pricing-signal.md) + the network policy.

Fixtures are short excerpts modelled on the real pages (measured 2026-10-05), padded with filler so they read as
a rendered page rather than a JS shell. No network.
"""
from __future__ import annotations

import httpx

from scout.pricing import (MAX_PAGE_REQUESTS, USER_AGENT, PricingFetcher, classify, pricing_link, registrable_domain,
                           visible_text)

FILLER = "<p>" + "Open source, self-hosted and privacy friendly. " * 15 + "</p>"


def page(body: str) -> str:
    return f"<html><head><title>x</title></head><body><nav>Docs Blog</nav>{FILLER}{body}</body></html>"


def cls(home_html, category="analytics", pricing_html=None, cfg=None):
    return classify(visible_text(home_html) if home_html is not None else None,
                    visible_text(pricing_html) if pricing_html is not None else None,
                    category, cfg, "https://example.com/", "https://example.com/pricing" if pricing_html else None)


# ------------------------------------------------------------------ 10 design cases
def test_01_talivia_selfserve(cfg):
    t = cls(page("<div>Pro <b>$9.99</b>/mo billed monthly</div>"), cfg=cfg)
    assert t[0] == "selfserve" and t[1] == 9.99


def test_02_plausible_spaces_lowest(cfg):
    t = cls(page("<span>$9</span>    /mo <span>$14</span>    /mo <span>$19</span>    /mo"), cfg=cfg)
    assert t[0] == "selfserve" and t[1] == 9


def test_03_taxhacker_euro_invoice_home_price_accepted(cfg):
    t = cls(page("<p>Cloud: €10/mo, cancel any time</p>"), category="invoice", cfg=cfg)
    assert t[0] == "selfserve" and 10 < t[1] < 12


def test_04_dittofeed_price_beats_sales_wording(cfg):
    t = cls(page("<a href='/pricing'>Pricing</a>"), pricing_html=page("<p>Growth $75/mo</p><a>Contact sales</a>"), cfg=cfg)
    assert t[0] == "pricey" and t[1] == 75 and t[2] == "https://example.com/pricing"


def test_05_sales_only(cfg):
    assert cls(page("<a class='btn'>Book a demo</a>"), cfg=cfg)[0] == "sales"


def test_06_paymenter_demo_shop_price_ignored_for_commerce(cfg):
    assert cls(page("<div class='plan'>Starter VPS $5/mo</div>"), category="commerce", cfg=cfg)[0] == "no_price"


def test_07_commerce_pricing_page_price_counts(cfg):
    t = cls(page("<div>Starter VPS $5/mo</div>"), category="commerce", pricing_html=page("<p>Pro license $29/mo</p>"), cfg=cfg)
    assert t[0] == "selfserve" and t[1] == 29


def test_08_spa_shell_unknown(cfg):
    shell = "<html><body><div id='root'></div><script src='/app.js'></script></body></html>"
    assert cls(shell, cfg=cfg)[0] == "unknown"


def test_09_pricing_link_same_registrable_domain_only():
    assert registrable_domain("docs.foo.com") == "foo.com" and registrable_domain("beenuar.github.io") == "beenuar.github.io"
    assert pricing_link('<a href="https://foo.com/pricing">P</a>', "https://docs.foo.com/") == "https://foo.com/pricing"
    assert pricing_link('<a href="https://other.com/pricing">P</a>', "https://docs.foo.com/") is None
    assert pricing_link('<a href="/#pricing">P</a>', "https://foo.com/") is None  # same page anchor


def test_10_price_only_inside_script_is_ignored(cfg):
    assert cls(page('<script>window.plans={"pro":"$12/mo"}</script>'), cfg=cfg)[0] == "no_price"


def test_yearly_price_is_divided_by_12(cfg):
    t = cls(page("<p>Team $240/year</p>"), cfg=cfg)
    assert t[0] == "selfserve" and t[1] == 20


# ------------------------------------------------------------------ network policy (CEO condition, fixed in code)
def _fetcher(handler):
    return PricingFetcher(transport=httpx.MockTransport(handler), check_url=lambda _u: None)


def test_network_policy_ua_cap_no_retry_robots(cfg):
    seen: list[httpx.Request] = []

    def ok(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private\n")
        if req.url.path == "/":
            return httpx.Response(200, headers={"content-type": "text/html"}, text=page('<a href="/pricing">Pricing</a>'))
        return httpx.Response(200, headers={"content-type": "text/html"}, text=page("<p>Pro $19/mo</p>"))

    f = _fetcher(ok)
    s = f.fetch("a/b", "https://foo.com/", "analytics", cfg)
    pages = [r for r in seen if r.url.path != "/robots.txt"]
    assert s.tier == "selfserve" and s.requests == len(pages) == MAX_PAGE_REQUESTS == 2
    assert all(r.headers["user-agent"] == USER_AGENT for r in seen)
    # robots.txt is cached per host: a second repo on the same host fetches it again 0 times
    f.fetch("a/c", "https://foo.com/", "analytics", cfg)
    assert sum(r.url.path == "/robots.txt" for r in seen) == 1

    # no retry: a server error is one request, then unknown
    calls: list[str] = []

    def boom(req: httpx.Request) -> httpx.Response:
        calls.append(req.url.path)
        return httpx.Response(200, text="") if req.url.path == "/robots.txt" else httpx.Response(503)

    s2 = _fetcher(boom).fetch("a/d", "https://bar.com/", "analytics", cfg)
    assert s2.tier == "unknown" and calls.count("/") == 1 and s2.requests == 1

    # robots.txt disallows the homepage path -> unknown, page never requested
    hits: list[str] = []

    def blocked(req: httpx.Request) -> httpx.Response:
        hits.append(req.url.path)
        return httpx.Response(200, text="User-agent: *\nDisallow: /\n")

    s3 = _fetcher(blocked).fetch("a/e", "https://baz.com/", "analytics", cfg)
    assert s3.tier == "unknown" and "robots" in s3.note and hits == ["/robots.txt"] and s3.requests == 0


def test_redirect_hop_is_robots_checked(cfg):
    # foo.com/ -> app.bar.com/ whose robots.txt disallows everything: the redirected page is never fetched
    seen: list[str] = []

    def h(req: httpx.Request) -> httpx.Response:
        seen.append(f"{req.url.host}{req.url.path}")
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /\n" if req.url.host == "app.bar.com" else "")
        if req.url.host == "foo.com":
            return httpx.Response(301, headers={"location": "https://app.bar.com/"})
        return httpx.Response(200, headers={"content-type": "text/html"}, text=page("<p>$9/mo</p>"))

    s = _fetcher(h).fetch("a/b", "https://foo.com/", "analytics", cfg)
    assert s.tier == "unknown" and "robots" in s.note and "app.bar.com/" not in seen


def test_same_site_redirect_still_reads(cfg):
    def h(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        if req.url.host == "foo.com":
            return httpx.Response(301, headers={"location": "https://www.foo.com/"})
        return httpx.Response(200, headers={"content-type": "text/html"}, text=page("<p>Pro $12/mo</p>"))

    s = _fetcher(h).fetch("a/b", "https://foo.com/", "analytics", cfg)
    assert s.tier == "selfserve" and s.requests == 1 and s.source_url == "https://www.foo.com/"


def test_non_public_hosts_are_blocked_before_any_request(cfg):
    from scout.pricing import Blocked, check_public_url
    import pytest

    for u in ("http://127.0.0.1/", "http://169.254.169.254/latest/meta-data/", "http://10.0.0.5/", "http://localhost/",
              "https://example.com:8443/", "ftp://example.com/", "http://example.com:abc/", "http://example.com:99999/"):
        with pytest.raises(Blocked):
            check_public_url(u)
    hit: list[str] = []
    f = PricingFetcher(transport=httpx.MockTransport(lambda r: hit.append(str(r.url)) or httpx.Response(200)))
    s = f.fetch("a/b", "http://169.254.169.254/", "analytics", cfg)
    assert s.tier == "unknown" and hit == [] and s.requests == 0


def test_body_is_cut_at_max_bytes(cfg):
    from scout import pricing

    big = page("<p>Pro $9/mo</p>") + "x" * (pricing.MAX_BYTES * 2)
    f = _fetcher(lambda r: httpx.Response(404) if r.url.path == "/robots.txt" else httpx.Response(200, headers={"content-type": "text/html"}, text=big))
    _r, text = f._get("https://foo.com/")
    assert len(text) <= pricing.MAX_BYTES


def test_no_homepage_is_unknown_without_requests(cfg):
    s = _fetcher(lambda r: httpx.Response(500)).fetch("a/b", None, "crm", cfg)
    assert s.tier == "unknown" and s.requests == 0
