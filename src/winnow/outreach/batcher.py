"""Group POSSIBLE candidates by outbound channel."""

from __future__ import annotations

from collections.abc import Sequence

from winnow.models import Candidate
from winnow.outreach.transport_linkedin import SECOND_CHANNEL

CHANNEL_PRIORITY: tuple[str, ...] = ("email", SECOND_CHANNEL, "dm")


def channel_priority_from_config(raw: dict | None) -> tuple[str, ...]:
    """Default email → second channel (linkedin unless config) → dm."""
    if raw is None:
        return CHANNEL_PRIORITY
    custom = raw.get("channel_priority")
    if isinstance(custom, (list, tuple)):
        return tuple(str(c) for c in custom)
    second = str(raw.get("second_channel", SECOND_CHANNEL))
    return ("email", second, "dm")


def primary_channel(
    candidate: Candidate,
    priority: tuple[str, ...] | None = None,
) -> str | None:
    """Pick one primary channel using configured priority order."""
    order = priority or CHANNEL_PRIORITY
    for key in order:
        value = candidate.contacts.get(key)
        if isinstance(value, str) and value.strip():
            return key
    return None


def recipient_for(candidate: Candidate, channel: str) -> str:
    return candidate.contacts[channel].strip()


def group_by_channel(
    candidates: Sequence[Candidate],
    priority: tuple[str, ...] | None = None,
) -> dict[str, list[Candidate]]:
    order = priority or CHANNEL_PRIORITY
    batches: dict[str, list[Candidate]] = {ch: [] for ch in order}
    for candidate in candidates:
        channel = primary_channel(candidate, priority=order)
        if channel is None:
            continue
        batches[channel].append(candidate)
    return {ch: rows for ch, rows in batches.items() if rows}