"""Human-readable operator feedback from outreach tracker data (no auto-tuning)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from winnow.outreach.tracker import OutreachRecord, OutreachTracker

# Operator tuning reference bounds (list size only — NOT criteria weights).
POSSIBLE_COUNT_TOO_LARGE = 50
POSSIBLE_COUNT_TOO_SMALL = 3


@dataclass(frozen=True, slots=True)
class TemplateStats:
    sent: int
    replied: int
    rate: float


TrackerPayload = Mapping[str, OutreachTracker | Sequence[OutreachRecord] | Mapping[str, int]]


def _stats_from_records(records: Sequence[OutreachRecord]) -> TemplateStats:
    sent = sum(1 for r in records if r.status == "sent")
    replied = sum(1 for r in records if r.status == "replied")
    rate = (replied / sent) if sent else 0.0
    return TemplateStats(sent=sent, replied=replied, rate=rate)


def ingest_replies(tracker_data: TrackerPayload) -> dict[str, TemplateStats]:
    """Aggregate sent/replied counts per template key (template name or version bucket)."""
    out: dict[str, TemplateStats] = {}
    for template_key, payload in tracker_data.items():
        if isinstance(payload, OutreachTracker):
            out[template_key] = _stats_from_records(payload.records)
            continue
        if isinstance(payload, Mapping):
            sent = int(payload.get("sent", 0))
            replied = int(payload.get("replied", 0))
            rate = (replied / sent) if sent else 0.0
            out[template_key] = TemplateStats(sent=sent, replied=replied, rate=rate)
            continue
        records = list(payload)
        if records and not isinstance(records[0], OutreachRecord):
            msg = f"expected OutreachRecord rows for {template_key!r}"
            raise TypeError(msg)
        out[template_key] = _stats_from_records(records)
    return out


def tune(
    template_name: str,
    stats: TemplateStats,
    *,
    possible_count: int | None = None,
    predicate_names: tuple[str, ...] = (),
) -> str:
    """Return a SUGGESTION string only; never mutates criteria or candidates."""
    del stats  # reserved for future operator copy; aggregate stats stay off Candidate

    if possible_count is not None:
        if possible_count > POSSIBLE_COUNT_TOO_LARGE:
            target = predicate_names[0] if predicate_names else "a predicate"
            return (
                f"SUGGESTION for {template_name!r}: POSSIBLE count ({possible_count}) "
                f"exceeds operator bound ({POSSIBLE_COUNT_TOO_LARGE}). "
                f"Tighten predicate {target!r} (add stricter bool rule — no weights)."
            )
        if possible_count < POSSIBLE_COUNT_TOO_SMALL:
            target = predicate_names[-1] if predicate_names else "a predicate"
            return (
                f"SUGGESTION for {template_name!r}: POSSIBLE count ({possible_count}) "
                f"is below operator bound ({POSSIBLE_COUNT_TOO_SMALL}). "
                f"Loosen predicate {target!r} (remove or relax a bool rule — no weights)."
            )

    return (
        f"SUGGESTION for {template_name!r}: no list-size change; "
        f"POSSIBLE count is within operator bounds "
        f"({POSSIBLE_COUNT_TOO_SMALL}–{POSSIBLE_COUNT_TOO_LARGE})."
    )