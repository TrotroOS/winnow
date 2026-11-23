from __future__ import annotations

from datetime import datetime, timezone

from winnow.adapters.fixture import FixtureSourceAdapter
from winnow.cli import main
from winnow.config import WinnowConfig
from winnow.orchestrator import run_winnow


def test_cli_run_json_with_fixture_pipeline(tmp_path, monkeypatch) -> None:
    now = datetime(2025, 6, 1, tzinfo=timezone.utc)
    records = [
        {
            "id": "1",
            "name": "Pat",
            "org": "Acme",
            "role": "CTO",
            "signals": {"sector": "b2b"},
            "contacts": {"email": "pat@acme.test"},
            "collected_at": now.isoformat(),
        },
    ]
    adapter = FixtureSourceAdapter("fixture_primary", records)

    monkeypatch.setattr("winnow.cli.resolve_adapters_from_env", lambda **_: [])

    def fake_run(situation, adapters, **kwargs):
        return run_winnow(
            situation,
            [adapter],
            config=WinnowConfig(0, None, None, None),
            audit_log_path=kwargs.get("audit_log_path"),
        )

    monkeypatch.setattr("winnow.cli.run_winnow", fake_run)
    code = main(["run", "--situation", "b2b launch CTO", "--json", "--audit-log", str(tmp_path / "a.jsonl")])
    assert code == 0


def test_full_dry_run_fixture_only(tmp_path) -> None:
    now = datetime(2025, 6, 1, tzinfo=timezone.utc)
    adapter = FixtureSourceAdapter(
        "fixture_primary",
        [
            {
                "id": "1",
                "name": "Pat",
                "org": "Acme",
                "role": "CTO",
                "signals": {"sector": "b2b saas", "geography": "ghana"},
                "contacts": {"email": "pat@acme.test"},
                "collected_at": now.isoformat(),
            },
            {
                "id": "2",
                "name": "No",
                "org": "Acme",
                "role": "Intern",
                "signals": {"sector": "b2b"},
                "contacts": {"email": "x@acme.test"},
                "collected_at": now.isoformat(),
            },
        ],
    )
    cfg = WinnowConfig(spend_cap_cents=0, enrichment_api_key=None, csv_source_dir=None, github_token=None)
    result = run_winnow(
        "B2B SaaS launch need CTO in Ghana",
        [adapter],
        config=cfg,
        audit_log_path=tmp_path / "audit.jsonl",
    )
    assert result.situation_type == "launch"
    assert len(result.possible) == 1
    assert result.possible[0].id == "1"
    assert result.outreach.sent == 1