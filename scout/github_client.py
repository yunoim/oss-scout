"""Thin GitHub REST wrapper: auth, rate-limit waits, search throttling, ETag cache."""
from __future__ import annotations

import base64
import json
import logging
import re
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

log = logging.getLogger(__name__)

API = "https://api.github.com"
DEPS_DEV = "https://api.deps.dev/v3"
SEARCH_PER_MINUTE = 30
MIN_REMAINING = 5


class TransientError(Exception):
    """Retryable HTTP condition (5xx, secondary rate limit, network hiccup)."""


class ETagCache:
    """Persistent ETag -> body cache, keyed by full URL (incl. query + accept)."""

    def __init__(self, path: Path | None):
        self.path = path
        self._lock = threading.Lock()
        self._data: dict[str, dict[str, Any]] = {}
        self.hits = 0
        if path and path.exists():
            try:
                self._data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                log.warning("etag cache unreadable, starting fresh: %s", path)
                self._data = {}

    def get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            return self._data.get(key)

    def put(self, key: str, etag: str, status: int, text: str, is_json: bool, link: str | None) -> None:
        with self._lock:
            entry: dict[str, Any] = {"etag": etag, "status": status, "text": text, "json": is_json, "ts": int(time.time())}
            if link:
                entry["link"] = link  # GitHub omits Link on 304; needed for contributor estimates
            self._data[key] = entry

    def save(self) -> None:
        if not self.path:
            return
        with self._lock:
            cutoff = int(time.time()) - 60 * 86400  # drop entries older than 60 days
            self._data = {k: v for k, v in self._data.items() if v.get("ts", 0) >= cutoff}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._data, ensure_ascii=False), encoding="utf-8")


class Response:
    __slots__ = ("status", "headers", "body", "text", "from_cache")

    def __init__(self, status: int, headers: dict[str, str], body: Any, text: str, from_cache: bool = False):
        self.status = status
        self.headers = headers
        self.body = body
        self.text = text
        self.from_cache = from_cache

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


class GitHubClient:
    def __init__(
        self,
        token: str | None,
        cache_path: Path | None = None,
        timeout: float = 30.0,
        sleep=time.sleep,
    ):
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "oss-scout/0.1",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.http = httpx.Client(headers=headers, timeout=timeout, follow_redirects=True)
        self.cache = ETagCache(cache_path)
        self._sleep = sleep
        self._search_times: deque[float] = deque()
        self._lock = threading.Lock()
        self.requests_made = 0

    # ------------------------------------------------------------------ core
    def _throttle_search(self) -> None:
        with self._lock:
            now = time.monotonic()
            while self._search_times and now - self._search_times[0] > 60:
                self._search_times.popleft()
            if len(self._search_times) >= SEARCH_PER_MINUTE:
                wait = 60 - (now - self._search_times[0]) + 0.5
                log.info("search throttle: sleeping %.1fs", wait)
                self._sleep(max(wait, 0))
            self._search_times.append(time.monotonic())

    def _respect_rate_limit(self, headers: httpx.Headers) -> None:
        try:
            remaining = int(headers.get("x-ratelimit-remaining", "999"))
            reset = int(headers.get("x-ratelimit-reset", "0"))
        except ValueError:
            return
        if remaining < MIN_REMAINING and reset:
            wait = max(reset - time.time(), 0) + 1
            log.warning("rate limit nearly exhausted (%s left); sleeping %.0fs", remaining, wait)
            self._sleep(wait)

    @retry(
        retry=retry_if_exception_type(TransientError),
        wait=wait_exponential(multiplier=2, min=2, max=90),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def _do_get(self, url: str, params: dict | None, accept: str | None) -> Response:
        key = url + ("?" + urlencode(sorted(params.items())) if params else "") + ("|" + accept if accept else "")
        cached = self.cache.get(key)
        headers: dict[str, str] = {}
        if accept:
            headers["Accept"] = accept
        if cached and cached.get("etag"):
            headers["If-None-Match"] = cached["etag"]
        if "/search/" in url:
            self._throttle_search()
        try:
            r = self.http.get(url, params=params, headers=headers)
        except httpx.HTTPError as e:
            raise TransientError(str(e)) from e
        self.requests_made += 1
        if url.startswith(API):
            self._respect_rate_limit(r.headers)

        if r.status_code == 304 and cached:
            self.cache.hits += 1
            text = cached.get("text", "")
            body = None
            if cached.get("json") and text:
                try:
                    body = json.loads(text)
                except json.JSONDecodeError:
                    body = None
            elif "body" in cached:  # legacy cache entries
                body = cached["body"]
            headers = dict(r.headers)
            if cached.get("link") and not headers.get("link"):
                headers["link"] = cached["link"]
            return Response(cached["status"], headers, body, text, from_cache=True)
        if r.status_code in (403, 429) and (
            "rate limit" in r.text.lower() or r.headers.get("retry-after") or r.headers.get("x-ratelimit-remaining") == "0"
        ):
            wait = int(r.headers.get("retry-after") or 0)
            if not wait:
                reset = int(r.headers.get("x-ratelimit-reset") or 0)
                wait = max(reset - int(time.time()), 0) + 1 if reset else 60
            log.warning("rate limited on %s; sleeping %ss", url, wait)
            self._sleep(min(wait, 900))
            raise TransientError("rate limited")
        if r.status_code >= 500:
            raise TransientError(f"{r.status_code} from {url}")

        text = r.text
        body: Any = None
        is_json = False
        if "json" in r.headers.get("content-type", "") and text:
            try:
                body = r.json()
                is_json = True
            except json.JSONDecodeError:
                body = None
        resp = Response(r.status_code, dict(r.headers), body, text)
        etag = r.headers.get("etag")
        if etag and r.status_code == 200:
            self.cache.put(key, etag, r.status_code, text, is_json, r.headers.get("link"))
        return resp

    def get(self, path: str, params: dict | None = None, accept: str | None = None) -> Response:
        url = path if path.startswith("http") else f"{API}{path}"
        return self._do_get(url, params, accept)

    def close(self) -> None:
        self.cache.save()
        self.http.close()

    # ------------------------------------------------------------ helpers
    def get_json(self, path: str, params: dict | None = None) -> Any | None:
        r = self.get(path, params)
        return r.body if r.ok else None

    def search_repositories(self, query: str, sort: str, page: int, per_page: int = 100) -> list[dict]:
        r = self.get(
            "/search/repositories",
            {"q": query, "sort": sort, "order": "desc", "page": page, "per_page": per_page},
        )
        if not r.ok:
            log.warning("search failed %s: %s", r.status, (r.text or "")[:200])
            return []
        return list((r.body or {}).get("items", []))

    def repo(self, full_name: str) -> dict | None:
        return self.get_json(f"/repos/{full_name}")

    def contents(self, full_name: str, path: str = "", ref: str | None = None) -> list[dict] | None:
        params = {"ref": ref} if ref else None
        r = self.get(f"/repos/{full_name}/contents/{path}", params)
        if not r.ok or not isinstance(r.body, list):
            return None
        return r.body

    def file_text(self, full_name: str, path: str, ref: str | None = None, max_bytes: int = 400_000) -> str | None:
        """Fetch a file's raw text via the contents API. Returns None if missing."""
        params = {"ref": ref} if ref else None
        r = self.get(f"/repos/{full_name}/contents/{path}", params, accept="application/vnd.github.raw+json")
        if not r.ok:
            return None
        text = r.text or ""
        if not text and isinstance(r.body, dict) and r.body.get("encoding") == "base64":
            text = base64.b64decode(r.body.get("content", "")).decode("utf-8", "replace")
        return text[:max_bytes] if text else None

    def readme_text(self, full_name: str) -> str | None:
        r = self.get(f"/repos/{full_name}/readme", accept="application/vnd.github.raw+json")
        if not r.ok:
            return None
        return r.text or None

    def license_file(self, full_name: str) -> tuple[str | None, str | None]:
        """Returns (spdx_id from GitHub detection, decoded license text)."""
        r = self.get(f"/repos/{full_name}/license")
        if not r.ok or not isinstance(r.body, dict):
            return None, None
        spdx = ((r.body.get("license") or {}).get("spdx_id")) or None
        content = r.body.get("content") or ""
        text = None
        if content and r.body.get("encoding") == "base64":
            try:
                text = base64.b64decode(content).decode("utf-8", "replace")
            except (ValueError, UnicodeDecodeError):
                text = None
        return spdx, text

    def releases(self, full_name: str, per_page: int = 5) -> list[dict] | None:
        r = self.get(f"/repos/{full_name}/releases", {"per_page": per_page})
        return r.body if r.ok and isinstance(r.body, list) else None

    def contributors_count(self, full_name: str) -> int | None:
        """Estimate contributor count from the Link header of a per_page=1 request."""
        r = self.get(f"/repos/{full_name}/contributors", {"per_page": 1, "anon": "true"})
        if r.status == 204:
            return 0
        if not r.ok:
            return None
        link = r.headers.get("link") or r.headers.get("Link") or ""
        m = re.search(r'[?&]page=(\d+)[^>]*>;\s*rel="last"', link)
        if m:
            return int(m.group(1))
        return len(r.body) if isinstance(r.body, list) else None

    # ------------------------------------------------------------- deps.dev
    def depsdev_licenses(self, system: str, name: str, version: str | None) -> list[str] | None:
        """Return license expressions for a package version; None if lookup failed."""
        base = f"{DEPS_DEV}/systems/{system}/packages/{quote(name, safe='')}"
        if not version:
            r = self.get(base)
            if not r.ok or not isinstance(r.body, dict):
                return None
            versions = r.body.get("versions") or []
            default = next((v for v in versions if v.get("isDefault")), None) or (versions[-1] if versions else None)
            if not default:
                return None
            version = (default.get("versionKey") or {}).get("version")
            if not version:
                return None
        r = self.get(f"{base}/versions/{quote(version, safe='')}")
        if not r.ok or not isinstance(r.body, dict):
            return None
        return list(r.body.get("licenses") or [])
