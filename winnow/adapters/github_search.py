"""GitHub user search source — skipped when token is absent."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from winnow.adapters.base import SourceAdapter

HttpGet = Callable[[str, dict[str, str]], bytes]


def _default_http_get(url: str, headers: dict[str, str]) -> bytes:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


class GitHubSearchSourceAdapter(SourceAdapter):
    """Paid/rate-limited API source; use only when ``WINNOW_GITHUB_TOKEN`` is set."""

    def __init__(
        self,
        token: str,
        query: str,
        *,
        cost_rank: int = 2,
        per_page: int = 30,
        http_get: HttpGet | None = None,
    ) -> None:
        self._token = token
        self._query = query
        self._cost_rank = cost_rank
        self._per_page = per_page
        self._http_get = http_get or _default_http_get

    @property
    def name(self) -> str:
        return "github:search_users"

    @property
    def cost_rank(self) -> int:
        return self._cost_rank

    def fetch_raw(self) -> list[dict[str, Any]]:
        params = urllib.parse.urlencode(
            {"q": self._query, "per_page": str(self._per_page)}
        )
        url = f"https://api.github.com/search/users?{params}"
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "winnow",
        }
        try:
            payload = json.loads(self._http_get(url, headers).decode("utf-8"))
        except (urllib.error.URLError, json.JSONDecodeError, UnicodeDecodeError):
            return []

        items = payload.get("items") or []
        records: list[dict[str, Any]] = []
        for item in items:
            login = str(item.get("login", ""))
            if not login:
                continue
            records.append(
                {
                    "id": f"github:{login}",
                    "name": login,
                    "org": str(item.get("company") or ""),
                    "role": "",
                    "signals": {"github_login": login, "source_kind": "github_user"},
                    "contacts": {"github": login},
                }
            )
        return records