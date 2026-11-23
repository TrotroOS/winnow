"""Human-readable operator feedback from outreach tracker data (no auto-tuning)."""

from __future__ import annotations

import json
import warnings
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from winnow.outreach.tracker import OutreachRecord, OutreachTracker

DEFAULT_FEEDBACK_LOG = Path("logs/feedback.jsonl")

# Operator reference thresholds (not criteria weights or scores).
LIST_SIZE_DAILY_CAP_MULTIPLIER = 3
REPLY_RATE_MIN = 0.02
BOUNCE_RATE_MAX = 0.03
POSSIBLE_COUNT_TOO_SMALL = 3


@dataclass(frozen=True, slots=True)
class TemplateStats:
    sent: int
    replied: int
    bounced: int = 0
    opt_out: int = 0

    @property
    def reply_rate(self) -> float:
        return (self.replied / self.sent) if self.sent else 0.0

    @property
    def bounce_rate(self) -> float:
        return (self.bounced / self.sent) if self.sent else 0.0

    @property
    def rate(self) -> float:
        """Alias for ``reply_rate`` (aggregate only)."""
        return self.reply_rate


def _stats_from_records(records: Sequence[OutreachRecord]) -> TemplateStats:
    sent = sum(1 for r in records if r.status == "sent")
    replied = sum(1 for r in records if r.status == "replied")
    bounced = sum(1 for r in records if r.status == "bounced")
    opt_out = sum(1 for r in records if r.status == "opt_out")
    return TemplateStats(sent=sent, replied=replied, bounced=bounced, opt_out=opt_out)


def ingest(tracker: OutreachTracker) -> dict[str, TemplateStats]:
    """Aggregate outreach outcomes per template bucket (``template_version`` key)."""
    buckets: dict[str, list[OutreachRecord]] = {}
    for record in tracker.records:
        buckets.setdefault(record.template_version, []).append(record)
    return {key: _stats_from_records(rows) for key, rows in buckets.items()}


def suggest(
    template_name: str,
    stats: TemplateStats,
    *,
    possible_count: int,
    daily_cap: int,
    predicate_names: tuple[str, ...] = (),
    matched_signal_hint: str = "matched_signal",
) -> str:
    """Return recommendation text only; never mutates criteria or candidates."""
    lines: list[str] = []
    list_cap = daily_cap * LIST_SIZE_DAILY_CAP_MULTIPLIER

    if possible_count > list_cap:
        target = predicate_names[0] if predicate_names else "a predicate"
        lines.append(
            f"SUGGESTION for {template_name!r}: POSSIBLE list ({possible_count}) "
            f"exceeds {list_cap} ({LIST_SIZE_DAILY_CAP_MULTIPLIER}× daily_cap). "
            f"Tighten predicate {target!r} (stricter bool rule — no weights)."
        )

    if possible_count < POSSIBLE_COUNT_TOO_SMALL:
        target = predicate_names[-1] if predicate_names else "a predicate"
        lines.append(
            f"SUGGESTION for {template_name!r}: POSSIBLE list ({possible_count}) "
            f"is below operator bound ({POSSIBLE_COUNT_TOO_SMALL}). "
            f"Loosen predicate {target!r} (relax bool rule — no weights)."
        )

    if stats.sent and stats.reply_rate < REPLY_RATE_MIN:
        lines.append(
            f"SUGGESTION for {template_name!r}: reply rate "
            f"{stats.reply_rate:.2%} is below {REPLY_RATE_MIN:.0%}. "
            f"Signal predicate likely wrong; review {matched_signal_hint!r} distribution."
        )

    if stats.sent and stats.bounce_rate > BOUNCE_RATE_MAX:
        lines.append(
            f"SUGGESTION for {template_name!r}: bounce rate "
            f"{stats.bounce_rate:.2%} exceeds {BOUNCE_RATE_MAX:.0%}. "
            "Verification failing; tighten reachability gate (hard bool gate only)."
        )

    if not lines:
        return (
            f"SUGGESTION for {template_name!r}: no operator action; "
            "metrics within reference bounds."
        )
    return "\n".join(lines)


def append_feedback_log(path: Path, entry: Mapping[str, object]) -> None:
    """Append one JSON object per line (append-only)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(entry), default=str) + "\n")


def emit_suggestions(
    text: str,
    *,
    log_path: Path = DEFAULT_FEEDBACK_LOG,
    template_name: str | None = None,
) -> None:
    """Print to console and append to ``logs/feedback.jsonl``."""
    print(text)
    payload: dict[str, object] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "suggestion": text,
    }
    if template_name is not None:
        payload["template"] = template_name
    append_feedback_log(log_path, payload)


# Backward-compatible names (deprecated).
TrackerPayload = Mapping[str, OutreachTracker | Sequence[OutreachRecord] | Mapping[str, int]]
POSSIBLE_COUNT_TOO_LARGE = 50  # legacy tests/reference only


def ingest_replies(tracker_data: TrackerPayload) -> dict[str, TemplateStats]:
    warnings.warn(
        "ingest_replies is deprecated; use ingest(OutreachTracker)",
        DeprecationWarning,
        stacklevel=2,
    )
    out: dict[str, TemplateStats] = {}
    for template_key, payload in tracker_data.items():
        if isinstance(payload, OutreachTracker):
            merged = OutreachTracker()
            merged.records.extend(payload.records)
            for version, row in ingest(merged).items():
                out[f"{template_key}:{version}" if version != template_key else template_key] = row
            continue
        if isinstance(payload, Mapping):
            sent = int(payload.get("sent", 0))
            replied = int(payload.get("replied", 0))
            bounced = int(payload.get("bounced", 0))
            opt_out = int(payload.get("opt_out", 0))
            out[template_key] = TemplateStats(sent, replied, bounced, opt_out)
            continue
        records = list(payload)
        out[template_key] = _stats_from_records(records)
    return out


def tune(
    template_name: str,
    stats: TemplateStats,
    *,
    possible_count: int | None = None,
    predicate_names: tuple[str, ...] = (),
) -> str:
    warnings.warn("tune is deprecated; use suggest()", DeprecationWarning, stacklevel=2)
    count = possible_count if possible_count is not None else 0
    return suggest(
        template_name,
        stats,
        possible_count=count,
        daily_cap=max(1, POSSIBLE_COUNT_TOO_LARGE // LIST_SIZE_DAILY_CAP_MULTIPLIER),
        predicate_names=predicate_names,
        matched_signal_hint="matched_signal",
    )