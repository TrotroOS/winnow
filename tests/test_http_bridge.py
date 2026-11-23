from __future__ import annotations

from winnow.http_bridge import describe_situation_payload, run_for_http


def test_describe_situation_binary_only() -> None:
    payload = describe_situation_payload("launch")
    assert payload["binary_only"] is True
    assert payload["situation_type"] == "launch"
    assert isinstance(payload["criteria_names"], list)
    assert "fit_score" not in payload
    assert "ranking" not in payload


def test_run_for_http_returns_audit_counts() -> None:
    payload = run_for_http("launch")
    assert payload["binary_only"] is True
    assert payload["possible_count"] == 1
    assert payload["noise_dropped"] == 1
    assert "audit_summary" in payload
    assert "rank" not in str(payload).lower()