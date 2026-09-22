"""Korea demand signals: issues/PRs on the upstream repo that mention Korean needs.

People who opened "Korean translation?" / "KakaoPay support?" issues already want the
localized product. This module counts them so the weekly report can rank candidates by
expressed demand, not just by license cleanliness.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel

from .config import Config
from .github_client import GitHubClient

log = logging.getLogger(__name__)


class SignalIssue(BaseModel):
    title: str
    url: str
    state: str
    is_pr: bool
    created_at: datetime | None = None
    reactions: int = 0


class DemandSignals(BaseModel):
    full_name: str
    fetched: bool = False
    total: int = 0          # issues + PRs matching
    issues: int = 0         # issues only (the demand side)
    prs: int = 0            # PRs (someone already tried to add it)
    open_issues: int = 0
    recent: int = 0         # created within `recent_days`
    reactions: int = 0      # sum of 👍 over the fetched sample
    latest_at: datetime | None = None
    top: list[SignalIssue] = []

    @property
    def score(self) -> int:
        """Simple ranking key: open + recent issues weigh more than old closed PRs."""
        return self.issues * 2 + self.open_issues * 2 + self.recent * 3 + self.prs + min(self.reactions, 20)


KINDS = ("issue", "pull-request")


def build_query(full_name: str, cfg: Config, kind: str = "issue") -> str:
    """Title-only match per keyword, one query per kind (issue / pull-request).

    Verified against the live API (2026-09):
    - `repo:X (a OR b) in:title` and `repo:X AND (a OR b) AND in:title` both degrade to "every issue in the
      repo" under advanced_search; attaching `in:title` to each term inside the group returns exact matches.
    - Body/comment matching was far too noisy ("toss out", ISO region tables, Korean in PR bodies).
    - Newer tokens (fine-grained PAT in Actions) get HTTP 422 "Query must include 'is:issue' or
      'is:pull-request'", so the kind qualifier is mandatory and we search the two kinds separately.
    """
    terms = " OR ".join(f"{k} in:title" for k in cfg.demand.keywords)
    return f"repo:{full_name} AND is:{kind} AND ({terms})"


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def fetch_signals(client: GitHubClient, full_name: str, cfg: Config, now: datetime | None = None) -> DemandSignals:
    now = now or datetime.now(timezone.utc)
    sig = DemandSignals(full_name=full_name)
    cutoff = now - timedelta(days=cfg.demand.recent_days)
    items: list[tuple[dict, bool]] = []
    for kind in KINDS:
        r = client.get(
            "/search/issues",
            {
                "q": build_query(full_name, cfg, kind),
                "sort": "reactions",
                "order": "desc",
                "per_page": cfg.demand.sample_size,
                "advanced_search": "true",
            },
        )
        if not r.ok or not isinstance(r.body, dict):
            log.warning("demand search failed for %s (%s): HTTP %s %s", full_name, kind, r.status,
                        (r.text or "")[:200].replace("\n", " "))
            continue
        sig.fetched = True
        sig.total += int(r.body.get("total_count") or 0)
        items += [(it, kind == "pull-request" or "pull_request" in it) for it in (r.body.get("items") or [])]
    for it, is_pr in items:
        created = _parse_dt(it.get("created_at"))
        plus1 = int(((it.get("reactions") or {}).get("+1")) or 0)
        issue = SignalIssue(
            title=(it.get("title") or "")[:140],
            url=it.get("html_url") or "",
            state=it.get("state") or "",
            is_pr=is_pr,
            created_at=created,
            reactions=plus1,
        )
        if is_pr:
            sig.prs += 1
        else:
            sig.issues += 1
            if issue.state == "open":
                sig.open_issues += 1
        if created and created >= cutoff:
            sig.recent += 1
        sig.reactions += plus1
        if created and (sig.latest_at is None or created > sig.latest_at):
            sig.latest_at = created
        sig.top.append(issue)
    # the sample may be smaller than total_count; keep counts consistent with what we saw
    sig.top.sort(key=lambda i: (i.state == "open", i.reactions, i.created_at or datetime.min.replace(tzinfo=timezone.utc)), reverse=True)
    sig.top = sig.top[: cfg.demand.top_issues]
    return sig
