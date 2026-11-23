from __future__ import annotations

from pathlib import Path

import pytest

from winnow.budget import SpendCapExceeded, SpendTracker


def test_record_raises_when_run_cap_exceeded(tmp_path: Path) -> None:
    tracker = SpendTracker(
        max_spend_per_run=50.0,
        max_spend_per_month=500.0,
        spend_log_path=tmp_path / "spend.json",
    )
    tracker.record(30.0)
    with pytest.raises(SpendCapExceeded):
        tracker.record(25.0)
    assert tracker.run_spent == pytest.approx(30.0)


def test_record_raises_when_month_cap_exceeded(tmp_path: Path) -> None:
    path = tmp_path / "spend.json"
    tracker = SpendTracker(
        max_spend_per_run=100.0,
        max_spend_per_month=60.0,
        spend_log_path=path,
    )
    tracker.record(30.0)
    with pytest.raises(SpendCapExceeded):
        tracker.record(35.0)
    assert tracker.month_spent == pytest.approx(30.0)


def test_remaining_reflects_caps(tmp_path: Path) -> None:
    tracker = SpendTracker(100.0, 1000.0, spend_log_path=tmp_path / "spend.json")
    tracker.record(25.5)
    run_left, month_left = tracker.remaining()
    assert run_left == pytest.approx(74.5)
    assert month_left == pytest.approx(974.5)


def test_monthly_persistence_survives_new_tracker_instance(tmp_path: Path) -> None:
    path = tmp_path / "spend.json"
    first = SpendTracker(200.0, 2000.0, spend_log_path=path)
    first.record(42.5)
    second = SpendTracker(200.0, 2000.0, spend_log_path=path)
    assert second.month_spent == pytest.approx(42.5)
    assert second.run_spent == 0.0
    _, month_left = second.remaining()
    assert month_left == pytest.approx(2000.0 - 42.5)