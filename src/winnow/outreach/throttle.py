"""Per-channel daily send caps."""

from __future__ import annotations

from datetime import date, datetime, timezone

DEFAULT_DAILY_CAPS: dict[str, int] = {
    "email": 50,
    "linkedin": 25,
    "dm": 20,
}


class Throttle:
    """Enforce daily caps per outreach channel (not weighted scoring)."""

    def __init__(
        self,
        caps: dict[str, int] | None = None,
        *,
        day: date | None = None,
    ) -> None:
        self._caps = dict(DEFAULT_DAILY_CAPS)
        if caps:
            self._caps.update(caps)
        self._counts: dict[str, int] = {ch: 0 for ch in self._caps}
        self._day = day or datetime.now(timezone.utc).date()

    @property
    def day(self) -> date:
        return self._day

    def allow(self, channel: str) -> bool:
        cap = self._caps.get(channel)
        if cap is None:
            return False
        return self._counts.get(channel, 0) < cap

    def record(self, channel: str) -> None:
        self._counts[channel] = self._counts.get(channel, 0) + 1

    def sent_today(self, channel: str) -> int:
        return self._counts.get(channel, 0)

    def reset_for_day(self, day: date) -> None:
        self._day = day
        self._counts = {ch: 0 for ch in self._caps}