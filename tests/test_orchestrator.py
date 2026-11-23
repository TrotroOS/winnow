from __future__ import annotations

from datetime import datetime, timezone

from winnow.adapters.fixture import FixtureSourceAdapter
from winnow.config import WinnowConfig
from winnow.orchestrator import run_winnow


def test_run_winnow_end_to_end_no_network(tmp_path) -> None:
    now = datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc)
    records = [
        {
            "id": "1",
            "name": "Pat",
            "org": "Acme",
            "role": "PM",
            "contacts": {"email": "pat@acme.test"},
            "collected_at": now.isoformat(),
        },
        {
            "id": "2",
            "name": "Q",
            "org": "",
            "role": "Eng",
            "contacts": {"email": "q@acme.test"},
            "collected_at": now.isoformat(),
        },
    ]
    adapter = FixtureSourceAdapter("fixture_primary", records)
    cfg = WinnowConfig(spend_cap_cents=100, enrichment_api_key=None)
    result = run_winnow(
        "launch",
        [adapter],
        config=cfg,
        audit_log_path=tmp_path / "audit.jsonl",
    )
    assert result.situation_type == "launch"
    assert len(result.possible) == 1
    assert result.noise_dropped == 1
    assert result.outreach.sent == 1
    assert (tmp_path / "audit.jsonl").exists()