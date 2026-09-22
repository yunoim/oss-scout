"""Persistent weekly state: star history, first/last seen, Notion status mirror."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def iso_week(dt: datetime | None = None) -> str:
    dt = dt or datetime.now(timezone.utc)
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


def _week_sort_key(week: str) -> tuple[int, int]:
    y, w = week.split("-W")
    return int(y), int(w)


class State:
    def __init__(self, data: dict[str, Any] | None = None, path: Path | None = None):
        self.path = path
        self.data: dict[str, Any] = data or {"version": 1, "weeks": [], "repos": {}}
        self.data.setdefault("version", 1)
        self.data.setdefault("weeks", [])
        self.data.setdefault("repos", {})

    # ------------------------------------------------------------------ io
    @classmethod
    def load(cls, path: Path) -> "State":
        if path.exists():
            try:
                return cls(json.loads(path.read_text(encoding="utf-8")), path)
            except (OSError, json.JSONDecodeError) as e:
                log.warning("state unreadable (%s); starting fresh", e)
        return cls(None, path)

    def save(self, path: Path | None = None) -> None:
        p = path or self.path
        if not p:
            raise ValueError("no path for state")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.data, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")

    # ------------------------------------------------------------------ queries
    @property
    def weeks(self) -> list[str]:
        return sorted(self.data["weeks"], key=_week_sort_key)

    def repo(self, full_name: str) -> dict[str, Any] | None:
        return self.data["repos"].get(full_name)

    def previous_stars(self, full_name: str, current_week: str) -> tuple[str, int] | None:
        """Most recent (week, stars) strictly before current_week, or None."""
        r = self.repo(full_name)
        if not r:
            return None
        hist = r.get("stars") or {}
        prior = [w for w in hist if _week_sort_key(w) < _week_sort_key(current_week)]
        if not prior:
            return None
        w = max(prior, key=_week_sort_key)
        return w, int(hist[w])

    def is_new(self, full_name: str, current_week: str) -> bool:
        r = self.repo(full_name)
        if not r:
            return True
        first = r.get("first_seen")
        return not first or _week_sort_key(first) >= _week_sort_key(current_week)

    def status(self, full_name: str) -> str | None:
        r = self.repo(full_name)
        return r.get("status") if r else None

    def rejected(self) -> set[str]:
        return {n for n, r in self.data["repos"].items() if (r.get("status") or "").lower() == "rejected"}

    # ------------------------------------------------------------------ updates
    def record(self, week: str, full_name: str, stars: int, score: int, excluded: bool = False,
               signals: int | None = None) -> None:
        repos = self.data["repos"]
        r = repos.setdefault(full_name, {"first_seen": week, "stars": {}, "score": {}})
        r.setdefault("first_seen", week)
        r["last_seen"] = week
        r.setdefault("stars", {})[week] = stars
        r.setdefault("score", {})[week] = score
        r["excluded"] = excluded
        if signals is not None:
            r["kr_signals"] = signals
        if week not in self.data["weeks"]:
            self.data["weeks"].append(week)

    def set_status(self, full_name: str, status: str | None) -> None:
        if status and full_name in self.data["repos"]:
            self.data["repos"][full_name]["status"] = status

    def prune(self, keep_weeks: int) -> None:
        weeks = self.weeks
        if len(weeks) <= keep_weeks:
            return
        keep = set(weeks[-keep_weeks:])
        self.data["weeks"] = sorted(keep, key=_week_sort_key)
        for name in list(self.data["repos"]):
            r = self.data["repos"][name]
            r["stars"] = {w: v for w, v in (r.get("stars") or {}).items() if w in keep}
            r["score"] = {w: v for w, v in (r.get("score") or {}).items() if w in keep}
            if not r["stars"] and (r.get("status") or "").lower() not in ("reviewing", "forked", "selling", "rejected"):
                del self.data["repos"][name]
