from __future__ import annotations

from datetime import datetime, timezone

from scout.state import State, iso_week


def test_iso_week():
    assert iso_week(datetime(2026, 9, 21, tzinfo=timezone.utc)) == "2026-W39"
    assert iso_week(datetime(2026, 1, 1, tzinfo=timezone.utc)) == "2026-W01"
    assert iso_week(datetime(2027, 1, 3, tzinfo=timezone.utc)) == "2026-W53"


def test_new_entry_and_growth(tmp_path):
    p = tmp_path / "state.json"
    s = State.load(p)
    assert s.is_new("a/b", "2026-W38")
    assert s.previous_stars("a/b", "2026-W38") is None

    s.record("2026-W38", "a/b", stars=1000, score=70)
    s.save()
    s2 = State.load(p)
    assert not s2.is_new("a/b", "2026-W39")
    assert s2.is_new("a/b", "2026-W38")  # first seen this very week -> still "new" for that week's report
    assert s2.is_new("c/d", "2026-W39")
    assert s2.previous_stars("a/b", "2026-W39") == ("2026-W38", 1000)

    s2.record("2026-W39", "a/b", stars=1100, score=72)
    s2.record("2026-W40", "a/b", stars=1300, score=75)
    assert s2.previous_stars("a/b", "2026-W40") == ("2026-W39", 1100)
    assert s2.previous_stars("a/b", "2026-W41") == ("2026-W40", 1300)
    assert s2.weeks == ["2026-W38", "2026-W39", "2026-W40"]
    assert s2.repo("a/b")["first_seen"] == "2026-W38"
    assert s2.repo("a/b")["last_seen"] == "2026-W40"


def test_status_and_rejected(tmp_path):
    s = State(path=tmp_path / "s.json")
    s.record("2026-W39", "a/b", 10, 50)
    s.record("2026-W39", "c/d", 10, 50)
    s.set_status("a/b", "Rejected")
    s.set_status("zz/unknown", "Rejected")  # ignored: not tracked
    assert s.rejected() == {"a/b"}
    assert s.status("c/d") is None


def test_prune_keeps_recent_and_reviewed(tmp_path):
    s = State(path=tmp_path / "s.json")
    for i, w in enumerate(["2026-W30", "2026-W31", "2026-W32", "2026-W33"]):
        s.record(w, "old/gone", 100 + i, 50)
    s.record("2026-W30", "old/kept", 5, 40)
    s.set_status("old/kept", "Reviewing")
    s.record("2026-W33", "new/here", 7, 60)
    s.prune(keep_weeks=2)
    assert s.weeks == ["2026-W32", "2026-W33"]
    assert set(s.repo("old/gone")["stars"]) == {"2026-W32", "2026-W33"}
    assert "old/kept" in s.data["repos"]  # status protects it even with no recent stars
    assert "new/here" in s.data["repos"]


def test_corrupt_state_starts_fresh(tmp_path):
    p = tmp_path / "state.json"
    p.write_text("{not json", encoding="utf-8")
    s = State.load(p)
    assert s.data["repos"] == {} and s.weeks == []
