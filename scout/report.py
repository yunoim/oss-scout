"""Markdown weekly report builder."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .audit import AuditResult
from .config import Config
from .demand import DemandSignals
from .discover import Candidate
from .score import ScoreBreakdown


@dataclass
class Entry:
    candidate: Candidate
    audit: AuditResult
    score: ScoreBreakdown
    demand: DemandSignals | None = None

    @property
    def signals(self) -> int:
        return self.demand.issues + self.demand.prs if self.demand and self.demand.fetched else 0


@dataclass
class RunSummary:
    week: str
    generated_at: datetime
    searched: int  # raw search hits
    prefiltered: dict[str, str]  # dropped before audit
    entries: list[Entry]  # everything that was audited (incl. excluded)
    rejected: set[str] = field(default_factory=set)  # Notion Status = Rejected
    notion_url: str | None = None
    report_url: str | None = None

    # ---- derived views
    @property
    def passed(self) -> list[Entry]:
        return sorted(
            (e for e in self.entries if not e.score.excluded),
            key=lambda e: (e.score.total, e.candidate.stars),
            reverse=True,
        )

    @property
    def excluded(self) -> list[Entry]:
        return [e for e in self.entries if e.score.excluded]

    def top(self, n: int) -> list[Entry]:
        return [e for e in self.passed if e.candidate.full_name not in self.rejected][:n]

    @property
    def new_entries(self) -> list[Entry]:
        return [e for e in self.passed if e.score.is_new]

    def rising(self, n: int) -> list[Entry]:
        with_growth = [e for e in self.passed if e.score.growth_ratio is not None and e.score.stars_delta and e.score.stars_delta > 0]
        return sorted(with_growth, key=lambda e: e.score.growth_ratio or 0, reverse=True)[:n]

    def demand_ranked(self, n: int) -> list[Entry]:
        with_demand = [e for e in self.passed if e.demand and e.demand.fetched and e.signals > 0 and e.candidate.full_name not in self.rejected]
        return sorted(with_demand, key=lambda e: (e.demand.score, e.score.total), reverse=True)[:n]  # type: ignore[union-attr]


# ------------------------------------------------------------------ formatting
def _repo_link(c: Candidate) -> str:
    return f"[{c.full_name}]({c.html_url})"


def _stars(e: Entry) -> str:
    s = f"{e.candidate.stars:,}"
    d = e.score.stars_delta
    if d is not None:
        s += f" ({'+' if d >= 0 else ''}{d:,})"
    return s


def _flags(a: AuditResult) -> str:
    f = a.flags()
    return ", ".join(f) if f else "—"


def _models(sb: ScoreBreakdown) -> str:
    return ", ".join(sb.models) if sb.models else "—"


def _conf(sb: ScoreBreakdown) -> str:
    return " ⚠️low-conf" if sb.confidence == "low" else ""


def _signals(e: Entry) -> str:
    if not e.demand or not e.demand.fetched:
        return "—"
    d = e.demand
    s = f"{d.issues}i/{d.prs}p"
    if d.open_issues:
        s += f" ({d.open_issues} open)"
    return s


def top_table(entries: list[Entry], start_rank: int = 1) -> str:
    lines = [
        "| # | Repo | Score | License | Stars (Δ7d) | Model | KR | 신호 | Flags |",
        "|---|------|------:|---------|------------:|-------|---:|------|-------|",
    ]
    for i, e in enumerate(entries, start_rank):
        lines.append(
            f"| {i} | {_repo_link(e.candidate)} | {e.score.total}{_conf(e.score)} | {e.audit.spdx or 'unknown'} | "
            f"{_stars(e)} | {_models(e.score)} | {e.score.korea_points} | {_signals(e)} | {_flags(e.audit)} |"
        )
    return "\n".join(lines)


def demand_section(entries: list[Entry]) -> list[str]:
    md = ["| Repo | Score | 이슈/PR | open | 최근 1년 | 👍 | 대표 이슈 |", "|------|------:|------:|-----:|--------:|---:|----------|"]
    for e in entries:
        d = e.demand
        assert d is not None
        links = " · ".join(f"[{'PR' if i.is_pr else 'issue'}{' 🟢' if i.state == 'open' else ''}]({i.url} \"{i.title.replace(chr(34), chr(39))}\")" for i in d.top)
        md.append(f"| {_repo_link(e.candidate)} | {e.score.total} | {d.issues}/{d.prs} | {d.open_issues} | {d.recent} | {d.reactions} | {links or '—'} |")
    return md


def detail_card(rank: int, e: Entry) -> str:
    c, a, s = e.candidate, e.audit, e.score
    comp = " · ".join(f"{k} {v:g}" for k, v in s.components.items())
    lines = [
        f"### {rank}. {_repo_link(c)} — {s.total}점{_conf(s)}",
        "",
        f"> {c.description or '(no description)'}",
        "",
        f"- **카테고리**: {s.category} · **언어**: {c.language or '?'} · **컨트리뷰터**: {c.contributors if c.contributors is not None else '?'} · "
        f"**최근 push**: {c.pushed_at.date() if c.pushed_at else '?'} · **최근 릴리즈**: {c.latest_release_at.date() if c.latest_release_at else '없음'}",
        f"- **점수 분해**: {comp}",
        f"- **라이선스**: {a.spdx or 'unknown'} ({a.license_status})"
        + (f" · restricted: {', '.join(a.restricted_terms)}" if a.restricted_terms else "")
        + (f" · README 언급: {', '.join(a.readme_terms)}" if a.readme_terms else ""),
        f"- **의존성**: {a.deps_system or '매니페스트 없음'} {a.deps_checked}/{a.deps_total} 검사 · unknown {a.unknown_deps}"
        + (f" · **copyleft_deps**: {', '.join(a.copyleft_deps)}" if a.copyleft_deps else ""),
    ]
    if a.has_ee_dir:
        lines.append(f"- **ee 폴더**: {', '.join(a.ee_dirs) or ', '.join(a.extra_license_files)}"
                     + (f" — “{a.ee_license_excerpt}”" if a.ee_license_excerpt else ""))
    if a.trademark_notice:
        lines.append("- **상표 고지 있음** → 리브랜딩 필수")
    sig = a.signals
    lines.append(
        f"- **한국 기회 {s.korea_points}/10**: ko 로케일 {'있음' if sig.korean_locale else ('없음' if sig.korean_locale is False else '미확인')} · "
        f"stripe {'O' if sig.has_stripe else 'X'} / 국내결제 {'O' if sig.has_kr_pay else 'X'} · 카카오/네이버 로그인 {'O' if sig.has_kr_login else 'X'}"
    )
    if e.demand and e.demand.fetched and e.signals:
        d = e.demand
        lines.append(f"- **한국 수요 신호**: 이슈 {d.issues} (open {d.open_issues}) · PR {d.prs} · 최근 1년 {d.recent}"
                     + (" · " + " · ".join(f"[{i.title[:40]}]({i.url})" for i in d.top[:2]) if d.top else ""))
    if s.unknowns:
        lines.append(f"- **미확인 항목**: {', '.join(s.unknowns)}")
    lines.append(f"- **다음 액션**: {s.next_action}")
    return "\n".join(lines)


def build_report(summary: RunSummary, cfg: Config) -> str:
    n = cfg.report.top_n
    top = summary.top(n)
    passed = summary.passed
    excluded = summary.excluded
    new = summary.new_entries
    rising = summary.rising(cfg.report.rising_n)

    md: list[str] = [
        f"# OSS Scout — {summary.week}",
        "",
        f"_생성: {summary.generated_at.strftime('%Y-%m-%d %H:%M UTC')} · 자동 판정이며 법률 자문이 아닙니다. 판매 전 LICENSE·NOTICE·상표 정책을 직접 확인하세요._",
        "",
        "## 요약",
        "",
        f"- 검색 히트: **{summary.searched}** · 사전 필터 제외: {len(summary.prefiltered)}",
        f"- 감사 대상: **{len(summary.entries)}** · 감사 통과: **{len(passed)}** · 제외: **{len(excluded)}**",
        f"- 신규 진입: **{len(new)}** · Notion Rejected 필터: {len(summary.rejected & {e.candidate.full_name for e in passed})}",
    ]
    if summary.notion_url:
        md.append(f"- Notion DB: {summary.notion_url}")
    md += ["", f"## Top {n}", ""]
    md.append(top_table(top) if top else "_통과 항목 없음_")

    md += ["", "## 신규 진입", ""]
    if new:
        md.append(top_table(new[:n]))
    else:
        md.append("_없음 (또는 첫 실행)_")

    md += ["", f"## 급상승 Top {cfg.report.rising_n}", ""]
    if rising:
        md.append("| Repo | Stars | Δ7d | 증가율 | Score |")
        md.append("|------|------:|----:|------:|------:|")
        for e in rising:
            md.append(f"| {_repo_link(e.candidate)} | {e.candidate.stars:,} | +{e.score.stars_delta:,} | {e.score.growth_ratio*100:.1f}% | {e.score.total} |")
    else:
        md.append("_star 히스토리 없음 (첫 주) 또는 증가 없음_")

    demand = summary.demand_ranked(10)
    checked = sum(1 for e in passed if e.demand and e.demand.fetched)
    md += ["", "## 한국 수요 신호 Top 10", ""]
    if demand:
        md.append(f"_상위 {checked}개 리포의 이슈·PR 에서 `korean · 한국어 · kakao · naver · toss` 등을 검색. 이슈 = 요청(수요), PR = 누군가 이미 시도._")
        md.append("")
        md += demand_section(demand)
    elif checked:
        md.append(f"_{checked}개 리포를 검사했지만 한국 관련 이슈·PR 이 없음_")
    else:
        md.append("_수요 신호 수집 비활성 또는 실패_")

    md += ["", "## 제외 목록", ""]
    if excluded or summary.prefiltered:
        md.append("| Repo | 사유 |")
        md.append("|------|------|")
        for e in sorted(excluded, key=lambda e: e.candidate.stars, reverse=True):
            md.append(f"| {_repo_link(e.candidate)} | {e.score.exclusion_reason} |")
        for name, reason in sorted(summary.prefiltered.items()):
            if reason in ("archived", "fork") or reason.startswith(("stale", "non-product", "name pattern", "no README")):
                continue  # noise; counted in summary only
            md.append(f"| {name} | {reason} |")
        # summarise the noisy pre-filter reasons in one line
        buckets: dict[str, int] = {}
        for reason in summary.prefiltered.values():
            key = reason.split(":")[0].split(" ")[0]
            buckets[key] = buckets.get(key, 0) + 1
        if buckets:
            md.append("")
            md.append("사전 필터: " + ", ".join(f"{k} {v}" for k, v in sorted(buckets.items(), key=lambda x: -x[1])))
    else:
        md.append("_없음_")

    md += ["", "## 상세 카드", ""]
    for i, e in enumerate(top, 1):
        md.append(detail_card(i, e))
        md.append("")
    return "\n".join(md).rstrip() + "\n"
