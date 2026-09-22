"""Notion database sink (Notion API 2025-09-03 via notion-client 3.x).

The database is keyed by the `Name` title (owner/repo). `Status` is never overwritten once set.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from ..config import Config, Env
from ..report import Entry, RunSummary

log = logging.getLogger(__name__)

DB_TITLE = "OSS Scout"
MODEL_OPTIONS = ["managed-hosting", "si-onprem", "korean-localization", "template-sale", "plugin-sale"]
FLAG_OPTIONS = ["ee_dir", "trademark", "restricted_terms", "copyleft_deps", "unknown", "readme_terms"]
STATUS_OPTIONS = ["New", "Reviewing", "Forked", "Selling", "Rejected"]
CATEGORY_OPTIONS = ["analytics", "crm", "commerce", "cms", "booking", "invoice", "notification", "monitoring",
                    "llm-workflow", "internal-tools", "devtool", "lib", "other"]


def schema_properties() -> dict:
    return {
        "Name": {"title": {}},
        "URL": {"url": {}},
        "Score": {"number": {"format": "number"}},
        "License": {"select": {"options": [{"name": n} for n in ["MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "0BSD", "Unlicense", "unknown"]]}},
        "Stars": {"number": {"format": "number"}},
        "Stars Δ7d": {"number": {"format": "number"}},
        "Category": {"select": {"options": [{"name": n} for n in CATEGORY_OPTIONS]}},
        "Model": {"multi_select": {"options": [{"name": n} for n in MODEL_OPTIONS]}},
        "KR Opportunity": {"number": {"format": "number"}},
        "KR Signals": {"number": {"format": "number"}},
        "KR Signal Issues": {"rich_text": {}},
        "Flags": {"multi_select": {"options": [{"name": n} for n in FLAG_OPTIONS]}},
        "Status": {"select": {"options": [{"name": n, "color": c} for n, c in
                              zip(STATUS_OPTIONS, ["blue", "yellow", "purple", "green", "red"])]}},
        "Last Seen": {"date": {}},
        "First Seen": {"date": {}},
        "Notes": {"rich_text": {}},
    }


def _rt(text: str) -> list[dict]:
    text = text[:1900]
    return [{"type": "text", "text": {"content": text}}] if text else []


def _links(items: list[tuple[str, str]]) -> list[dict]:
    """Rich text made of linked titles separated by ' · ' (Notion caps each text run at 2000 chars)."""
    out: list[dict] = []
    for idx, (title, url) in enumerate(items):
        if idx:
            out.append({"type": "text", "text": {"content": " · "}})
        out.append({"type": "text", "text": {"content": title[:120], "link": {"url": url}}})
    return out


def _title(text: str) -> list[dict]:
    return [{"type": "text", "text": {"content": text[:200]}}]


def _week_monday(week: str) -> str:
    y, w = week.split("-W")
    return datetime.fromisocalendar(int(y), int(w), 1).date().isoformat()


def _plain_title(page: dict) -> str:
    prop = (page.get("properties") or {}).get("Name") or {}
    return "".join(t.get("plain_text", "") for t in prop.get("title") or [])


class NotionSink:
    def __init__(self, env: Env, client=None):
        from notion_client import Client

        self.env = env
        self.client = client or Client(auth=env.notion_token)
        self.database_id: str | None = env.notion_database_id
        self.data_source_id: str | None = None
        self.database_url: str | None = None
        self._pages: dict[str, dict] = {}  # full_name -> {"id", "status", "first_seen"}

    # ------------------------------------------------------------ setup
    def ensure_database(self) -> None:
        if self.database_id:
            db = self.client.databases.retrieve(self.database_id)
        else:
            if not self.env.notion_parent_page_id:
                raise RuntimeError("NOTION_DATABASE_ID or NOTION_PARENT_PAGE_ID required")
            log.info("creating Notion database under page %s", self.env.notion_parent_page_id)
            db = self.client.databases.create(
                parent={"type": "page_id", "page_id": self.env.notion_parent_page_id},
                title=_title(DB_TITLE),
                initial_data_source={"properties": schema_properties()},
            )
            self.database_id = db["id"]
            log.warning("Notion DB created: %s — set NOTION_DATABASE_ID=%s to reuse it", db.get("url"), db["id"])
        self.database_url = db.get("url")
        sources = db.get("data_sources") or []
        if not sources:
            raise RuntimeError("database has no data sources")
        self.data_source_id = sources[0]["id"]
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        ds = self.client.data_sources.retrieve(self.data_source_id)
        existing = ds.get("properties") or {}
        missing = {k: v for k, v in schema_properties().items() if k not in existing and k != "Name"}
        if missing:
            log.info("adding missing Notion properties: %s", sorted(missing))
            self.client.data_sources.update(self.data_source_id, properties=missing)

    # ------------------------------------------------------------ read
    def fetch_statuses(self) -> dict[str, str]:
        """Load all pages once; return {full_name: Status} for pages that have a Status."""
        self._pages = {}
        cursor = None
        while True:
            kwargs = {"page_size": 100}
            if cursor:
                kwargs["start_cursor"] = cursor
            resp = self.client.data_sources.query(self.data_source_id, **kwargs)
            for page in resp.get("results", []):
                name = _plain_title(page)
                if not name:
                    continue
                props = page.get("properties") or {}
                status = ((props.get("Status") or {}).get("select") or {}).get("name")
                first_seen = ((props.get("First Seen") or {}).get("date") or {}).get("start")
                self._pages[name.lower()] = {"id": page["id"], "status": status, "first_seen": first_seen}
            if not resp.get("has_more"):
                break
            cursor = resp.get("next_cursor")
        return {n: p["status"] for n, p in self._pages.items() if p.get("status")}

    # ------------------------------------------------------------ write
    def _properties(self, e: Entry, week: str, first_seen: str | None, set_status: bool) -> dict:
        c, a, s = e.candidate, e.audit, e.score
        lic = a.spdx if a.spdx in ["MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "0BSD", "Unlicense"] else "unknown"
        notes = " · ".join(f"{k} {v:g}" for k, v in s.components.items())
        if s.excluded:
            notes = f"EXCLUDED: {s.exclusion_reason}"
        elif s.next_action:
            notes += f" | 다음: {s.next_action}"
        if a.copyleft_deps:
            notes += f" | copyleft_deps: {', '.join(a.copyleft_deps[:5])}"
        props = {
            "Name": {"title": _title(c.full_name)},
            "URL": {"url": c.html_url},
            "Score": {"number": s.total},
            "License": {"select": {"name": lic}},
            "Stars": {"number": c.stars},
            "Stars Δ7d": {"number": s.stars_delta if s.stars_delta is not None else None},
            "Category": {"select": {"name": s.category if s.category in CATEGORY_OPTIONS else "other"}},
            "Model": {"multi_select": [{"name": m} for m in s.models if m in MODEL_OPTIONS]},
            "KR Opportunity": {"number": s.korea_points},
            "Flags": {"multi_select": [{"name": f} for f in a.flags() if f in FLAG_OPTIONS]},
            "Last Seen": {"date": {"start": _week_monday(week)}},
            "First Seen": {"date": {"start": first_seen or _week_monday(week)}},
            "Notes": {"rich_text": _rt(notes)},
        }
        if e.demand and e.demand.fetched:
            d = e.demand
            props["KR Signals"] = {"number": d.issues + d.prs}
            props["KR Signal Issues"] = {"rich_text": _links(
                [(("[PR] " if i.is_pr else "") + ("🟢 " if i.state == "open" else "") + i.title, i.url) for i in d.top]
            )}
        if set_status:
            props["Status"] = {"select": {"name": "New"}}
        return props

    def upsert(self, summary: RunSummary, cfg: Config) -> dict[str, str]:
        """Upsert every audited entry that passed, plus excluded ones already present. Returns statuses."""
        if not self._pages:
            self.fetch_statuses()
        statuses: dict[str, str] = {}
        created = updated = 0
        for e in summary.entries:
            name = e.candidate.full_name
            existing = self._pages.get(name.lower())
            if e.score.excluded and not existing:
                continue  # don't pollute the DB with traps we never tracked
            if existing:
                props = self._properties(e, summary.week, existing.get("first_seen"), set_status=not existing.get("status"))
                self.client.pages.update(existing["id"], properties=props)
                statuses[name] = existing.get("status") or "New"
                updated += 1
            else:
                props = self._properties(e, summary.week, None, set_status=True)
                page = self.client.pages.create(parent={"type": "data_source_id", "data_source_id": self.data_source_id}, properties=props)
                self._pages[name.lower()] = {"id": page["id"], "status": "New", "first_seen": _week_monday(summary.week)}
                statuses[name] = "New"
                created += 1
        log.info("Notion upsert: %d created, %d updated", created, updated)
        return statuses
