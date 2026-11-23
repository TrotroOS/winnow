"""Group POSSIBLE candidates by outbound channel."""

from __future__ import annotations

from collections.abc import Sequence

from winnow.models import Candidate

CHANNEL_PRIORITY: tuple[str, ...] = ("email", "linkedin", "dm")


def primary_channel(candidate: Candidate) -> str | None:
    """Pick one primary channel: email, else linkedin, else dm (first non-empty contact)."""
    for key in CHANNEL_PRIORITY:
        value = candidate.contacts.get(key)
        if isinstance(value, str) and value.strip():
            return key
    return None


def recipient_for(candidate: Candidate, channel: str) -> str:
    return candidate.contacts[channel].strip()


def group_by_channel(
    candidates: Sequence[Candidate],
) -> dict[str, list[Candidate]]:
    batches: dict[str, list[Candidate]] = {ch: [] for ch in CHANNEL_PRIORITY}
    for candidate in candidates:
        channel = primary_channel(candidate)
        if channel is None:
            continue
        batches[channel].append(candidate)
    return {ch: rows for ch, rows in batches.items() if rows}