"""Load and validate config.yaml plus environment secrets."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = ROOT / "config.yaml"
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"


class DiscoveryConfig(BaseModel):
    queries: list[str] = Field(min_length=1)
    sorts: list[str] = ["stars", "updated"]
    pages_per_query: int = 2
    per_page: int = 100
    max_push_age_days: int = 90
    max_candidates: int | None = 200
    refresh_repo_detail: bool = False
    exclude_topics: list[str] = []
    exclude_name_patterns: list[str] = []

    @field_validator("sorts")
    @classmethod
    def _valid_sorts(cls, v: list[str]) -> list[str]:
        allowed = {"stars", "updated", "forks", "help-wanted-issues"}
        bad = [s for s in v if s not in allowed]
        if bad:
            raise ValueError(f"unsupported search sort(s): {bad}")
        return v


class AuditConfig(BaseModel):
    ok_licenses: list[str]
    copyleft_patterns: list[str]
    copyleft_spdx: list[str]
    restricted_term_patterns: list[str]
    ee_dir_names: list[str] = ["ee", "enterprise", "premium", "pro"]
    ee_parent_dirs: list[str] = ["packages", "apps"]
    max_deps: int = 60
    dep_copyleft_pattern: str = r"(^|[^A-Za-z])(AGPL|GPL|SSPL|BUSL)"
    trademark_patterns: list[str] = ["trademark", "™", "®", "brand guidelines"]


class LicenseScoreConfig(BaseModel):
    ok: int = 20
    unknown: int = 8
    ee_dir_penalty: int = 5


class ActivityScoreConfig(BaseModel):
    recent_push_days: int = 14
    recent_push_points: int = 10
    release_within_days: int = 90
    release_points: int = 5


class PopularityScoreConfig(BaseModel):
    log_stars_points: int = 8
    log_stars_max: float = 5.0
    growth_points: int = 7
    growth_full_ratio: float = 0.05


class CommunityScoreConfig(BaseModel):
    contributors_threshold: int = 20
    contributors_points: int = 5
    issue_ratio_points: int = 5
    issue_ratio_bad: float = 0.05


class DeployScoreConfig(BaseModel):
    dockerfile: int = 5
    compose: int = 5
    helm_or_env: int = 3
    single_binary: int = 2


class CategoryScoreConfig(BaseModel):
    default_weight: int = 8
    weights: dict[str, int]
    keywords: dict[str, list[str]]


class KoreaScoreConfig(BaseModel):
    no_korean_locale: int = 4
    stripe_without_kr_pay: int = 3
    no_kr_social_login: int = 3
    i18n_dirs: list[str]
    korean_locale_markers: list[str]
    max_i18n_listings: int = 4


class ModelsConfig(BaseModel):
    korea_threshold: int = 7
    saas_categories: list[str]
    onprem_categories: list[str]
    plugin_dirs: list[str] = ["plugins", "extensions", "integrations", "addons", "modules"]
    plugin_min_stars: int = 8000


class ScoringConfig(BaseModel):
    weights: dict[str, int]
    license: LicenseScoreConfig = LicenseScoreConfig()
    activity: ActivityScoreConfig = ActivityScoreConfig()
    popularity: PopularityScoreConfig = PopularityScoreConfig()
    community: CommunityScoreConfig = CommunityScoreConfig()
    deploy: DeployScoreConfig = DeployScoreConfig()
    category: CategoryScoreConfig
    korea: KoreaScoreConfig
    models: ModelsConfig
    confidence_low_unknowns: int = 3

    @model_validator(mode="after")
    def _weights_sum_100(self) -> "ScoringConfig":
        required = {"license", "activity", "popularity", "community", "deploy", "category", "korea"}
        missing = required - set(self.weights)
        if missing:
            raise ValueError(f"scoring.weights missing: {sorted(missing)}")
        total = sum(self.weights.values())
        if total != 100:
            raise ValueError(f"scoring.weights must sum to 100, got {total}")
        return self


class DemandConfig(BaseModel):
    enabled: bool = True
    max_repos: int = 60
    sample_size: int = 30
    recent_days: int = 365
    top_issues: int = 3
    keywords: list[str] = ["korean", "한국어", "korea", "kakao", "naver", "toss"]


class ReportConfig(BaseModel):
    top_n: int = 15
    mail_top_n: int = 10
    rising_n: int = 5
    timezone: str = "Asia/Seoul"


class StateConfig(BaseModel):
    history_weeks: int = 26


class Config(BaseModel):
    discovery: DiscoveryConfig
    audit: AuditConfig
    known_traps: dict[str, str] = {}
    scoring: ScoringConfig
    demand: DemandConfig = DemandConfig()
    report: ReportConfig = ReportConfig()
    state: StateConfig = StateConfig()

    @field_validator("known_traps")
    @classmethod
    def _lower_keys(cls, v: dict[str, str]) -> dict[str, str]:
        return {k.lower(): str(reason) for k, reason in v.items()}


class Env(BaseModel):
    """Secrets and runtime environment, read from os.environ (and .env if present)."""

    github_token: str | None = None
    notion_token: str | None = None
    notion_database_id: str | None = None
    notion_parent_page_id: str | None = None
    smtp_user: str | None = None
    smtp_app_password: str | None = None
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    mail_to: str | None = None
    github_repository: str | None = None  # owner/repo hosting the reports (set by Actions)

    @property
    def notion_enabled(self) -> bool:
        return bool(self.notion_token and (self.notion_database_id or self.notion_parent_page_id))

    @property
    def mail_enabled(self) -> bool:
        return bool(self.smtp_user and self.smtp_app_password and self.mail_to)


def load_config(path: Path | str | None = None) -> Config:
    p = Path(path) if path else DEFAULT_CONFIG_PATH
    with open(p, encoding="utf-8") as fh:
        raw: dict[str, Any] = yaml.safe_load(fh) or {}
    return Config.model_validate(raw)


def _gh_cli_token() -> str | None:
    """Fallback for local runs: reuse the token the GitHub CLI keeps in its keyring (`gh auth token`)."""
    import shutil
    import subprocess

    gh = shutil.which("gh") or next(
        (p for p in (r"C:\Program Files\GitHub CLI\gh.exe",) if Path(p).exists()), None
    )
    if not gh:
        return None
    try:
        out = subprocess.run([gh, "auth", "token"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    token = out.stdout.strip()
    return token if out.returncode == 0 and token else None


def load_env(dotenv_path: Path | str | None = None) -> Env:
    try:
        from dotenv import load_dotenv

        load_dotenv(dotenv_path or ROOT / ".env", override=False)
    except ImportError:  # python-dotenv is optional
        pass

    def _get(*names: str) -> str | None:
        for n in names:
            v = os.environ.get(n)
            if v and v.strip():
                return v.strip()
        return None

    return Env(
        github_token=_get("GITHUB_TOKEN", "GH_TOKEN") or _gh_cli_token(),
        notion_token=_get("NOTION_TOKEN"),
        notion_database_id=_get("NOTION_DATABASE_ID"),
        notion_parent_page_id=_get("NOTION_PARENT_PAGE_ID"),
        smtp_user=_get("SMTP_USER"),
        smtp_app_password=_get("SMTP_APP_PASSWORD"),
        smtp_host=_get("SMTP_HOST") or "smtp.gmail.com",
        smtp_port=int(_get("SMTP_PORT") or 587),
        mail_to=_get("MAIL_TO"),
        github_repository=_get("GITHUB_REPOSITORY", "REPORT_REPOSITORY"),
    )
