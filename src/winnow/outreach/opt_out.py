"""Unsubscribe link and reply-based opt-out."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from winnow.outreach.suppression import SuppressionStore
    from winnow.outreach.tracker import OutreachTracker
    from winnow.store import WinnowStore


def reply_indicates_opt_out(text: str) -> bool:
    normalized = " ".join(text.strip().upper().split())
    if not normalized:
        return False
    if normalized in {"UNSUBSCRIBE", "OPT OUT", "OPT-OUT", "STOP"}:
        return True
    if normalized.startswith("UNSUBSCRIBE"):
        return True
    if "OPT OUT" in normalized or "OPT-OUT" in normalized:
        return True
    return False


def apply_opt_out(
    candidate_id: str,
    *,
    template_version: str,
    store: WinnowStore | None = None,
    suppression: SuppressionStore | None = None,
    tracker: OutreachTracker | None = None,
) -> None:
    if store is not None:
        store.set_candidate_status(candidate_id, "opted_out")
        store.ensure_suppression_hash(candidate_id)
    if suppression is not None:
        suppression.mark_opted_out(candidate_id)
    if tracker is not None:
        tracker.record_opt_out(candidate_id, template_version=template_version)