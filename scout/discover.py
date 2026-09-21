"""Candidate discovery via GitHub Search + per-repo enrichment."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel

from .config import Config
from .github_client import GitHubClient

log = logging.getLogger(__name__)

README_RE = re.compile(r"^readme(\.|$)", re.IGNORECASE)


class Candidate(BaseModel):
    full_name: str
    html_url: str
    description: str | None = None
    language: str | None = None
    stars: int = 0
    forks: int = 0
    open_issues: int = 0
    pushed_at: datetime | None = None
    archived: bool = False
    fork: bool = False
    topics: list[str] = []
    default_branch: str = "main"
    license_spdx: str | None = None
    # enrichment
    root_files: list[str] = []
    root_dirs: list[str] = []
    has_readme: bool = True
    latest_release_at: datetime | None = None
    releases_fetched: bool = False
    contributors: int | None = None
    matched_queries: list[str] = []

    @property
    def owner(self) -> str:
        return self.full_name.split("/")[0]

    @property
    def name(self) -> str:
        return self.full_name.split("/")[1]


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def candidate_from_api(item: dict) -> Candidate:
    lic = item.get("license") or {}
    return Candidate(
        full_name=item["full_name"],
        html_url=item.get("html_url") or f"https://github.com/{item['full_name']}",
        description=item.get("description"),
        language=item.get("language"),
        stars=int(item.get("stargazers_count") or 0),
        forks=int(item.get("forks_count") or 0),
        open_issues=int(item.get("open_issues_count") or 0),
        pushed_at=_parse_dt(item.get("pushed_at")),
        archived=bool(item.get("archived")),
        fork=bool(item.get("fork")),
        topics=[t.lower() for t in (item.get("topics") or [])],
        default_branch=item.get("default_branch") or "main",
        license_spdx=lic.get("spdx_id") if isinstance(lic, dict) else None,
    )


def render_queries(cfg: Config, now: datetime | None = None) -> list[str]:
    """Replace {Nd} placeholders with ISO dates N days before now."""
    now = now or datetime.now(timezone.utc)

    def sub(m: re.Match) -> str:
        days = int(m.group(1))
        return (now - timedelta(days=days)).date().isoformat()

    return [re.sub(r"\{(\d+)d\}", sub, q) for q in cfg.discovery.queries]


def prefilter_reason(c: Candidate, cfg: Config, now: datetime) -> str | None:
    """Return a reason string if the candidate should be dropped before enrichment."""
    d = cfg.discovery
    if c.archived:
        return "archived"
    if c.fork:
        return "fork"
    if c.pushed_at and (now - c.pushed_at).days > d.max_push_age_days:
        return f"stale (>{d.max_push_age_days}d)"
    bad_topics = set(t.lower() for t in d.exclude_topics) & set(c.topics)
    if bad_topics:
        return f"non-product topic: {','.join(sorted(bad_topics))}"
    for pat in d.exclude_name_patterns:
        if re.search(pat, c.name, re.IGNORECASE):
            return f"name pattern {pat}"
    return None


def search_candidates(client: GitHubClient, cfg: Config, now: datetime | None = None) -> dict[str, Candidate]:
    """Run all queries x sorts x pages and return the union keyed by full_name."""
    now = now or datetime.now(timezone.utc)
    d = cfg.discovery
    found: dict[str, Candidate] = {}
    for q in render_queries(cfg, now):
        for sort in d.sorts:
            for page in range(1, d.pages_per_query + 1):
                items = client.search_repositories(q, sort=sort, page=page, per_page=d.per_page)
                for it in items:
                    name = it["full_name"]
                    if name in found:
                        if q not in found[name].matched_queries:
                            found[name].matched_queries.append(q)
                        continue
                    c = candidate_from_api(it)
                    c.matched_queries = [q]
                    found[name] = c
                if len(items) < d.per_page:
                    break
            log.info("query done: %-70s sort=%-8s total=%d", q[:70], sort, len(found))
    return found


def enrich(client: GitHubClient, c: Candidate, refresh_detail: bool = True) -> Candidate:
    """Fetch repo detail (optional), root listing, releases and contributor estimate."""
    detail = client.repo(c.full_name) if refresh_detail else None
    if detail:
        fresh = candidate_from_api(detail)
        for f in ("stars", "forks", "open_issues", "pushed_at", "archived", "fork", "topics", "default_branch",
                  "license_spdx", "description", "language", "html_url"):
            setattr(c, f, getattr(fresh, f))

    listing = client.contents(c.full_name, "", ref=c.default_branch)
    if listing is not None:
        c.root_files = [e["name"] for e in listing if e.get("type") == "file"]
        c.root_dirs = [e["name"] for e in listing if e.get("type") == "dir"]
        c.has_readme = any(README_RE.match(f) for f in c.root_files)
    else:
        c.has_readme = False

    rels = client.releases(c.full_name, per_page=5)
    if rels is not None:
        c.releases_fetched = True
        dates = [_parse_dt(r.get("published_at") or r.get("created_at")) for r in rels if not r.get("draft")]
        dates = [d for d in dates if d]
        c.latest_release_at = max(dates) if dates else None

    c.contributors = client.contributors_count(c.full_name)
    return c


def discover(
    client: GitHubClient,
    cfg: Config,
    limit: int | None = None,
    now: datetime | None = None,
) -> tuple[list[Candidate], dict[str, str], int]:
    """Return (enriched candidates, prefilter-dropped {name: reason}, raw search hit count)."""
    now = now or datetime.now(timezone.utc)
    found = search_candidates(client, cfg, now)
    raw_count = len(found)
    dropped: dict[str, str] = {}
    kept: list[Candidate] = []
    for name, c in found.items():
        reason = prefilter_reason(c, cfg, now)
        if reason:
            dropped[name] = reason
        else:
            kept.append(c)
    kept.sort(key=lambda x: x.stars, reverse=True)
    cap = limit or cfg.discovery.max_candidates
    if cap:
        kept = kept[:cap]
    log.info("search hits=%d prefiltered=%d enriching=%d", raw_count, len(dropped), len(kept))

    enriched: list[Candidate] = []
    for i, c in enumerate(kept, 1):
        try:
            enrich(client, c, refresh_detail=cfg.discovery.refresh_repo_detail)
        except Exception as e:  # noqa: BLE001 - one bad repo must not kill the run
            log.warning("enrich failed for %s: %s", c.full_name, e)
        reason = prefilter_reason(c, cfg, now)  # re-check with fresh detail
        if reason:
            dropped[c.full_name] = reason
            continue
        if not c.has_readme:
            dropped[c.full_name] = "no README"
            continue
        enriched.append(c)
        if i % 10 == 0:
            log.info("enriched %d/%d (api calls=%d, etag hits=%d)", i, len(kept), client.requests_made, client.cache.hits)
    return enriched, dropped, raw_count
