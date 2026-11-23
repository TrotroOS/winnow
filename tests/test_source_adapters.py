from __future__ import annotations

import json
from datetime import datetime, timezone

from winnow.adapters.csv_directory import CsvDirectorySourceAdapter
from winnow.adapters.fixture import FixtureSourceAdapter
from winnow.adapters.github_search import GitHubSearchSourceAdapter
from winnow.source_router import COST_RANK_CSV, COST_RANK_FIXTURE, COST_RANK_GITHUB, order_adapters


def test_csv_directory_reads_files(tmp_path) -> None:
    csv_path = tmp_path / "people.csv"
    csv_path.write_text(
        "id,name,org,role,contacts_email\n"
        "10,Taylor,OrgCo,PM,taylor@org.test\n",
        encoding="utf-8",
    )
    adapter = CsvDirectorySourceAdapter(tmp_path)
    rows = adapter.fetch_raw()
    assert len(rows) == 1
    assert rows[0]["name"] == "Taylor"
    assert adapter.cost_rank == COST_RANK_CSV


def test_github_adapter_uses_injected_http() -> None:
    payload = {
        "items": [
            {"login": "octocat", "company": "GitHub"},
        ]
    }

    def fake_http(url: str, headers: dict[str, str]) -> bytes:
        assert "search/users" in url
        assert headers["Authorization"] == "Bearer test-token"
        return json.dumps(payload).encode()

    adapter = GitHubSearchSourceAdapter("test-token", "cto fintech", http_get=fake_http)
    records = adapter.fetch_raw()
    assert len(records) == 1
    assert records[0]["id"] == "github:octocat"
    assert adapter.cost_rank == COST_RANK_GITHUB


def test_cost_order_fixture_before_csv_before_github() -> None:
    fixture = FixtureSourceAdapter("f", [], cost_rank=COST_RANK_FIXTURE)
    csv = CsvDirectorySourceAdapter("/tmp/unused", cost_rank=COST_RANK_CSV)

    def fake_http(url: str, headers: dict[str, str]) -> bytes:
        return b'{"items":[]}'

    github = GitHubSearchSourceAdapter("t", "q", http_get=fake_http, cost_rank=COST_RANK_GITHUB)
    ordered = order_adapters([github, csv, fixture])
    assert [a.cost_rank for a in ordered] == [0, 1, 2]