"""Outreach safety: kill switch and audit-based auto_send refusal."""

from __future__ import annotations

import json
import os
from pathlib import Path

BOUNCE_RATE_MAX = 0.03
AUDIT_RUN_LOOKBACK = 3


def sends_halted() -> bool:
    """``WINNOW_HALT=1`` (or true/yes) blocks all outbound sends."""
    value = os.environ.get("WINNOW_HALT", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _tail_audit_entries(path: Path, n: int) -> list[dict]:
    if not path.is_file():
        return []
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    entries: list[dict] = []
    for line in lines[-n:]:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def audit_blocks_auto_send(audit_log_path: Path) -> tuple[bool, str]:
    """True when recent runs show bounce > 3% or zero replies (with sends)."""
    runs = _tail_audit_entries(audit_log_path, AUDIT_RUN_LOOKBACK)
    if not runs:
        return False, ""
    for entry in reversed(runs):
        outreach = entry.get("outreach", {})
        if not isinstance(outreach, dict):
            continue
        sent = int(outreach.get("sent", 0))
        if sent <= 0:
            continue
        replied = int(outreach.get("replied", 0))
        bounced = int(outreach.get("bounced", 0))
        bounce_rate = bounced / sent
        if replied == 0:
            return True, f"zero replies on last run with sent={sent}"
        if bounce_rate > BOUNCE_RATE_MAX:
            return (
                True,
                f"bounce rate {bounce_rate:.2%} exceeds {BOUNCE_RATE_MAX:.0%} "
                f"(sent={sent}, bounced={bounced})",
            )
    return False, ""


def resolve_manual_approve(
    outreach_mode: str,
    *,
    audit_log_path: Path,
    outreach_channels: tuple[str, ...] = (),
) -> tuple[bool, str | None]:
    """Return ``(manual_approve, optional_warning)`` for outreach mode resolution."""
    mode = outreach_mode.strip().lower()
    if mode in {"manual_approve", "manual", "approve"}:
        return True, None
    if mode != "auto_send":
        return True, f"WARNING: unknown outreach_mode {outreach_mode!r}; using manual_approve."

    from winnow.outreach.transport_linkedin import enforce_linkedin_manual_only

    linkedin_warning = enforce_linkedin_manual_only(outreach_mode, outreach_channels)
    if linkedin_warning:
        return True, linkedin_warning

    if sends_halted():
        return True, "WARNING: WINNOW_HALT is set; auto_send disabled (manual_approve)."

    blocked, reason = audit_blocks_auto_send(audit_log_path)
    if blocked:
        return (
            True,
            f"WARNING: auto_send refused ({reason}); falling back to manual_approve.",
        )
    return False, None