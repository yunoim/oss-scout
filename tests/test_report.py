from __future__ import annotations

from scout.audit import AuditResult, Signals
from scout.report import Entry, RunSummary, build_report
from scout.score import ScoreBreakdown, score_candidate
from scout.sinks.mail import build_html, build_subject
from tests.conftest import NOW, make_candidate


def _entry(cfg, name, stars, *, excluded=False, reason=None, prev=None, is_new=True, ee=False):
    c = make_candidate(full_name=name, stars=stars)
    if excluded:
        a = AuditResult(full_name=name, license_status="copyleft_or_restricted", excluded=True, exclusion_reason=reason)
    else:
        a = AuditResult(full_name=name, license_status="ok", spdx="MIT", readme_fetched=True, deps_system="npm", deps_total=3, deps_checked=3,
                        has_ee_dir=ee, ee_dirs=["ee"] if ee else [], ee_license_excerpt="Enterprise license applies" if ee else None,
                        signals=Signals(korean_locale=False, has_stripe=True, auth_mentioned=True))
    sb = score_candidate(c, a, cfg, prev_stars=prev, is_new=is_new, now=NOW)
    return Entry(c, a, sb)


def _summary(cfg):
    entries = [
        _entry(cfg, "acme/top", 12_000, prev=("2026-W38", 10_000), is_new=False),
        _entry(cfg, "acme/new", 3_000, ee=True),
        _entry(cfg, "acme/rejected", 9_000, is_new=False),
        _entry(cfg, "evil/agpl", 50_000, excluded=True, reason="copyleft_or_restricted: AGPL-3.0"),
        _entry(cfg, "n8n-io/n8n", 60_000, excluded=True, reason="known_trap: Sustainable Use License"),
    ]
    return RunSummary(week="2026-W39", generated_at=NOW, searched=500, prefiltered={"x/awesome-list": "name pattern ^awesome-", "y/old": "archived"},
                      entries=entries, rejected={"acme/rejected"}, notion_url="https://notion.so/db", report_url="https://github.com/o/r/blob/main/reports/2026-W39.md")


def test_markdown_sections(cfg):
    md = build_report(_summary(cfg), cfg)
    assert md.startswith("# OSS Scout — 2026-W39")
    assert "## Top 15" in md and "## 신규 진입" in md and "## 급상승 Top 5" in md and "## 제외 목록" in md and "## 상세 카드" in md
    # top table rows and rejected filtering
    assert "| 1 | [acme/top](https://github.com/acme/top) |" in md
    assert "acme/rejected" not in md.split("## Top 15")[1].split("## 신규 진입")[0]
    assert "12,000 (+2,000)" in md
    # excluded with reasons
    assert "| [evil/agpl](https://github.com/evil/agpl) | copyleft_or_restricted: AGPL-3.0 |" in md
    assert "known_trap: Sustainable Use License" in md
    # detail card content
    assert "ee 폴더" in md and "Enterprise license applies" in md
    assert "점수 분해" in md and "다음 액션" in md
    assert "https://notion.so/db" in md


def test_new_and_rising(cfg):
    s = _summary(cfg)
    assert [e.candidate.full_name for e in s.new_entries] == ["acme/new"]
    rising = s.rising(5)
    assert [e.candidate.full_name for e in rising] == ["acme/top"]
    assert abs(rising[0].score.growth_ratio - 0.2) < 1e-9


def test_empty_run(cfg):
    md = build_report(RunSummary(week="2026-W39", generated_at=NOW, searched=0, prefiltered={}, entries=[]), cfg)
    assert "_통과 항목 없음_" in md and "## 제외 목록" in md


def test_mail_subject_and_html(cfg):
    s = _summary(cfg)
    subject = build_subject(s, cfg)
    assert subject.startswith("[OSS Scout] 2026-W39 — Top: acme/top (")
    html = build_html(s, cfg)
    assert "<table" in html and "acme/top" in html and "acme/rejected" not in html
    assert "https://notion.so/db" in html and "reports/2026-W39.md" in html
    assert "법률 자문" in html


def test_score_breakdown_serialisable():
    sb = ScoreBreakdown(full_name="a/b", total=1)
    assert sb.model_dump()["full_name"] == "a/b"
