"""Per-run and monthly spend caps with durable monthly totals."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_SPEND_LOG = Path("logs/spend.json")


class SpendCapExceeded(Exception):
    """Recording ``cost`` would exceed the per-run or monthly cap."""


@dataclass
class SpendTracker:
    max_spend_per_run: float
    max_spend_per_month: float
    spend_log_path: Path = DEFAULT_SPEND_LOG
    run_spent: float = field(default=0.0, init=False)
    month_spent: float = field(default=0.0, init=False)
    _period: str = field(default="", init=False)

    def __post_init__(self) -> None:
        self._period = _current_period()
        self.month_spent = _load_month_spent(self.spend_log_path, self._period)

    def remaining(self) -> tuple[float, float]:
        """Return (remaining_this_run, remaining_this_month) in currency units."""
        run_left = self.max_spend_per_run - self.run_spent
        month_left = self.max_spend_per_month - self.month_spent
        return (max(0.0, run_left), max(0.0, month_left))

    def can_afford(self, cost: float) -> bool:
        if cost < 0:
            return False
        run_left, month_left = self.remaining()
        return cost <= run_left and cost <= month_left

    def record(self, cost: float) -> None:
        """Add ``cost`` to run and month totals; persist month spend."""
        if cost < 0:
            raise ValueError("cost must be non-negative")
        if self.run_spent + cost > self.max_spend_per_run:
            raise SpendCapExceeded(
                f"per-run cap {self.max_spend_per_run}; "
                f"would reach {self.run_spent + cost}"
            )
        if self.month_spent + cost > self.max_spend_per_month:
            raise SpendCapExceeded(
                f"per-month cap {self.max_spend_per_month}; "
                f"would reach {self.month_spent + cost}"
            )
        self.run_spent += cost
        self.month_spent += cost
        _save_month_spent(self.spend_log_path, self._period, self.month_spent)


def _current_period() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _load_month_spent(path: Path, period: str) -> float:
    if not path.exists():
        return 0.0
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return 0.0
    if raw.get("period") != period:
        return 0.0
    value = raw.get("month_spent", 0.0)
    return float(value)


def _save_month_spent(path: Path, period: str, month_spent: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"period": period, "month_spent": month_spent}
    path.write_text(json.dumps(payload), encoding="utf-8")