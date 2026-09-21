"""CLI entry point.

    python -m scout.main run [--dry-run] [--limit N] [--no-notion] [--no-mail]
    python -m scout.main audit owner/repo
    python -m scout.main score owner/repo
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from .audit import Auditor
from .config import DATA_DIR, REPORTS_DIR, Config, Env, load_config, load_env
from .discover import Candidate, candidate_from_api, discover, enrich
from .github_client import GitHubClient
from .report import Entry, RunSummary, build_report
from .score import score_candidate
from .state import State, iso_week

log = logging.getLogger("scout")


def _client(env: Env) -> GitHubClient:
    if not env.github_token:
        log.warning("GITHUB_TOKEN not set — unauthenticated requests are limited to 60/hour and 10 searches/min")
    return GitHubClient(env.github_token, cache_path=DATA_DIR / "etag_cache.json")


def _single_candidate(client: GitHubClient, full_name: str) -> Candidate:
    detail = client.repo(full_name)
    if not detail:
        raise SystemExit(f"repo not found or inaccessible: {full_name}")
    c = candidate_from_api(detail)
    return enrich(client, c)


# ------------------------------------------------------------------ commands
def cmd_run(args: argparse.Namespace, cfg: Config, env: Env) -> int:
    now = datetime.now(timezone.utc)
    week = iso_week(now)
    client = _client(env)
    state = State.load(DATA_DIR / "state.json")
    try:
        candidates, dropped, raw = discover(client, cfg, limit=args.limit, now=now)
        auditor = Auditor(client, cfg)
        entries: list[Entry] = []
        for i, c in enumerate(candidates, 1):
            try:
                a = auditor.audit(c)
            except Exception as e:  # noqa: BLE001
                log.warning("audit failed for %s: %s", c.full_name, e)
                continue
            sb = score_candidate(
                c, a, cfg,
                prev_stars=state.previous_stars(c.full_name, week),
                is_new=state.is_new(c.full_name, week),
                now=now,
            )
            entries.append(Entry(c, a, sb))
            log.info("[%d/%d] %-45s %3d %s%s", i, len(candidates), c.full_name, sb.total,
                     a.spdx or "?", " EXCLUDED" if sb.excluded else "")
        log.info("api calls=%d etag hits=%d", client.requests_made, client.cache.hits)
    finally:
        client.close()

    summary = RunSummary(week=week, generated_at=now, searched=raw, prefiltered=dropped, entries=entries,
                         rejected=state.rejected(), report_url=_report_url(env, week))

    notion_sink = None
    if not args.dry_run and not args.no_notion:
        if env.notion_enabled:
            try:
                from .sinks.notion import NotionSink

                notion_sink = NotionSink(env)
                notion_sink.ensure_database()
                statuses = notion_sink.fetch_statuses()
                for name, st in statuses.items():
                    state.set_status(name, st)
                summary.rejected |= {n for n, s in statuses.items() if s.lower() == "rejected"}
                summary.notion_url = notion_sink.database_url
            except Exception as e:  # noqa: BLE001
                log.warning("Notion unavailable, skipping sink: %s", e)
                notion_sink = None
        else:
            log.warning("Notion not configured (NOTION_TOKEN + NOTION_DATABASE_ID/NOTION_PARENT_PAGE_ID) — skipping")

    md = build_report(summary, cfg)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"{week}.md"
    out.write_text(md, encoding="utf-8")
    log.info("report written: %s (%d entries, %d passed)", out, len(entries), len(summary.passed))

    if args.dry_run:
        log.info("dry-run: state not written, sinks skipped")
        return 0

    for e in entries:
        state.record(week, e.candidate.full_name, e.candidate.stars, e.score.total, e.score.excluded)
    state.prune(cfg.state.history_weeks)
    state.save()

    if notion_sink:
        try:
            statuses = notion_sink.upsert(summary, cfg)
            for name, st in statuses.items():
                state.set_status(name, st)
            state.save()
        except Exception as e:  # noqa: BLE001
            log.warning("Notion upsert failed: %s", e)

    if not args.no_mail:
        if env.mail_enabled:
            try:
                from .sinks.mail import send_summary

                send_summary(summary, cfg, env)
            except Exception as e:  # noqa: BLE001
                log.warning("mail failed: %s", e)
        else:
            log.warning("mail not configured (SMTP_USER, SMTP_APP_PASSWORD, MAIL_TO) — skipping")
    return 0


def _report_url(env: Env, week: str) -> str | None:
    if env.github_repository:
        return f"https://github.com/{env.github_repository}/blob/main/reports/{week}.md"
    return None


def cmd_audit(args: argparse.Namespace, cfg: Config, env: Env) -> int:
    client = _client(env)
    try:
        c = _single_candidate(client, args.repo)
        res = Auditor(client, cfg).audit(c)
    finally:
        client.close()
    out = res.model_dump()
    out["flags"] = res.flags()
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def cmd_score(args: argparse.Namespace, cfg: Config, env: Env) -> int:
    client = _client(env)
    now = datetime.now(timezone.utc)
    state = State.load(DATA_DIR / "state.json")
    try:
        c = _single_candidate(client, args.repo)
        a = Auditor(client, cfg).audit(c)
    finally:
        client.close()
    week = iso_week(now)
    sb = score_candidate(c, a, cfg, prev_stars=state.previous_stars(c.full_name, week),
                         is_new=state.is_new(c.full_name, week), now=now)
    out = sb.model_dump()
    out["audit"] = {"license_status": a.license_status, "spdx": a.spdx, "flags": a.flags(),
                    "copyleft_deps": a.copyleft_deps, "unknown_deps": a.unknown_deps, "deps_checked": a.deps_checked,
                    "ee_dirs": a.ee_dirs, "signals": a.signals.model_dump()}
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


# ------------------------------------------------------------------ parser
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="scout", description="OSS Scout — weekly permissive-license OSS discovery")
    p.add_argument("--config", type=Path, default=None, help="path to config.yaml")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="discover → audit → score → report → sinks")
    r.add_argument("--dry-run", action="store_true", help="write reports/ only; no state, Notion or mail")
    r.add_argument("--limit", type=int, default=None, help="max candidates to enrich/audit")
    r.add_argument("--no-notion", action="store_true")
    r.add_argument("--no-mail", action="store_true")
    r.set_defaults(func=cmd_run)

    a = sub.add_parser("audit", help="audit a single owner/repo and print JSON")
    a.add_argument("repo")
    a.set_defaults(func=cmd_audit)

    s = sub.add_parser("score", help="audit + score a single owner/repo and print the breakdown")
    s.add_argument("repo")
    s.set_defaults(func=cmd_score)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    cfg = load_config(args.config)
    env = load_env()
    return args.func(args, cfg, env)


if __name__ == "__main__":
    sys.exit(main())
