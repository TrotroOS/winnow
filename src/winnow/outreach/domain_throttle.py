"""Per-recipient-domain send rate (messages per hour)."""

from __future__ import annotations

from datetime import datetime, timezone


def recipient_domain(address: str) -> str:
    part = address.strip().rsplit("@", 1)
    if len(part) != 2 or not part[1]:
        return ""
    return part[1].lower()


class RecipientDomainThrottle:
    """Cap sends per mailbox provider domain per UTC hour."""

    def __init__(self, max_per_hour: int = 20) -> None:
        self._max = max(1, max_per_hour)
        self._counts: dict[tuple[str, int], int] = {}

    def _hour_key(self, when: datetime) -> int:
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return int(when.astimezone(timezone.utc).timestamp() // 3600)

    def allow(self, recipient: str, *, now: datetime | None = None) -> bool:
        domain = recipient_domain(recipient)
        if not domain:
            return False
        when = now or datetime.now(timezone.utc)
        key = (domain, self._hour_key(when))
        return self._counts.get(key, 0) < self._max

    def record(self, recipient: str, *, now: datetime | None = None) -> None:
        domain = recipient_domain(recipient)
        if not domain:
            return
        when = now or datetime.now(timezone.utc)
        key = (domain, self._hour_key(when))
        self._counts[key] = self._counts.get(key, 0) + 1