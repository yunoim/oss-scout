"""Gmail SMTP (STARTTLS + app password) weekly summary mail."""
from __future__ import annotations

import html
import logging
import smtplib
from email.message import EmailMessage

from ..config import Config, Env
from ..report import Entry, RunSummary

log = logging.getLogger(__name__)


def _esc(s: object) -> str:
    return html.escape(str(s if s is not None else ""))


def _row(i: int, e: Entry) -> str:
    c, a, s = e.candidate, e.audit, e.score
    delta = f" (+{s.stars_delta:,})" if s.stars_delta is not None and s.stars_delta >= 0 else (f" ({s.stars_delta:,})" if s.stars_delta is not None else "")
    flags = ", ".join(a.flags()) or "—"
    return (
        f"<tr><td>{i}</td><td><a href='{_esc(c.html_url)}'>{_esc(c.full_name)}</a></td>"
        f"<td align='right'><b>{s.total}</b>{'<sup>low</sup>' if s.confidence == 'low' else ''}</td>"
        f"<td>{_esc(a.spdx or 'unknown')}</td><td align='right'>{c.stars:,}{_esc(delta)}</td>"
        f"<td>{_esc(', '.join(s.models) or '—')}</td><td align='right'>{s.korea_points}</td><td>{_esc(flags)}</td></tr>"
    )


def _table(entries: list[Entry]) -> str:
    if not entries:
        return "<p><i>없음</i></p>"
    head = "<tr><th>#</th><th>Repo</th><th>Score</th><th>License</th><th>Stars (Δ7d)</th><th>Model</th><th>KR</th><th>Flags</th></tr>"
    rows = "".join(_row(i, e) for i, e in enumerate(entries, 1))
    return f"<table border='1' cellpadding='6' cellspacing='0' style='border-collapse:collapse;font-size:13px'>{head}{rows}</table>"


def build_subject(summary: RunSummary, cfg: Config) -> str:
    top = summary.top(1)
    if top:
        return f"[OSS Scout] {summary.week} — Top: {top[0].candidate.full_name} ({top[0].score.total})"
    return f"[OSS Scout] {summary.week} — 통과 항목 없음"


def build_html(summary: RunSummary, cfg: Config) -> str:
    top = summary.top(cfg.report.mail_top_n)
    new = summary.new_entries[: cfg.report.mail_top_n]
    passed = summary.passed
    parts = [
        "<html><body style='font-family:-apple-system,Segoe UI,sans-serif;color:#222'>",
        f"<h2>OSS Scout — {_esc(summary.week)}</h2>",
        "<ul>",
        f"<li>검색 히트 {summary.searched} · 사전 필터 제외 {len(summary.prefiltered)}</li>",
        f"<li>감사 대상 {len(summary.entries)} · 통과 {len(passed)} · 제외 {len(summary.excluded)}</li>",
        f"<li>신규 진입 {len(summary.new_entries)}</li>",
        f"<li>1위: {_esc(top[0].candidate.full_name) if top else '—'} ({top[0].score.total if top else 0}점)</li>",
        "</ul>",
        f"<h3>Top {cfg.report.mail_top_n}</h3>",
        _table(top),
        "<h3>신규 진입</h3>",
        _table(new),
        "<p>",
    ]
    if summary.notion_url:
        parts.append(f"<a href='{_esc(summary.notion_url)}'>Notion DB</a> · ")
    if summary.report_url:
        parts.append(f"<a href='{_esc(summary.report_url)}'>리포트 전문 (GitHub)</a>")
    parts.append("</p><p style='color:#888;font-size:12px'>자동 판정이며 법률 자문이 아닙니다. 판매 전 LICENSE·NOTICE·상표 정책을 직접 확인하세요.</p>")
    parts.append("</body></html>")
    return "".join(parts)


def send_summary(summary: RunSummary, cfg: Config, env: Env, smtp_factory=smtplib.SMTP) -> None:
    msg = EmailMessage()
    msg["Subject"] = build_subject(summary, cfg)
    msg["From"] = env.smtp_user
    msg["To"] = env.mail_to
    msg.set_content(f"OSS Scout {summary.week} — HTML 메일을 지원하는 클라이언트에서 열어주세요.")
    msg.add_alternative(build_html(summary, cfg), subtype="html")
    with smtp_factory(env.smtp_host, env.smtp_port, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(env.smtp_user, env.smtp_app_password)
        smtp.send_message(msg)
    log.info("mail sent to %s: %s", env.mail_to, msg["Subject"])
