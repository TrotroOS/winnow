"""LinkedIn outreach transport — MANUAL ONLY (never auto_send)."""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from winnow.models import Candidate, Criteria
from winnow.outreach.personalize import MatchedSignalError, matched_signal

SECOND_CHANNEL = "linkedin"
DEFAULT_LINKEDIN_DAILY_CAP = 20
DEFAULT_MATCHED_SIGNAL_MAX_AGE_DAYS = 30

LINKEDIN_AUTO_SEND_REFUSAL = (
    "LinkedIn outreach is MANUAL ONLY: automated sends violate platform ToS "
    "and risk account bans. Use manual_approve and send connections by hand."
)


class LinkedInConfigError(RuntimeError):
    """Missing or invalid LinkedIn provider configuration."""


class LinkedInDeliveryError(RuntimeError):
    """Provider rejected or failed the send."""


class LinkedInProvider(Protocol):
    """Injectable client (real or fake in tests)."""

    def send_message(
        self,
        profile_url: str,
        body: str,
        *,
        candidate_id: str,
    ) -> str:
        """Queue or record a manual LinkedIn message; return provider id."""


def announce_linkedin_manual_only(*, stream: object = sys.stderr) -> None:
    print(LINKEDIN_AUTO_SEND_REFUSAL, file=stream)  # type: ignore[arg-type]


def linkedin_blocks_auto_send(outreach_channels: tuple[str, ...]) -> bool:
    """True when auto_send must be refused because LinkedIn is in scope."""
    return SECOND_CHANNEL in outreach_channels


def enforce_linkedin_manual_only(
    outreach_mode: str,
    outreach_channels: tuple[str, ...],
) -> str | None:
    """Print refusal and return warning text when auto_send would touch LinkedIn."""
    mode = outreach_mode.strip().lower()
    if mode != "auto_send":
        return None
    if not linkedin_blocks_auto_send(outreach_channels):
        return None
    announce_linkedin_manual_only()
    return (
        "WARNING: LinkedIn is manual-only (ToS/ban risk); "
        "auto_send disabled (manual_approve)."
    )


def _parse_activity_days(candidate: Candidate) -> int | None:
    raw = candidate.signals.get("activity_days", "")
    text = raw.strip() if isinstance(raw, str) else ""
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def matched_signal_is_recent(
    candidate: Candidate,
    criteria: Sequence[Criteria],
    *,
    now: datetime | None,
    max_age_days: int,
) -> bool:
    """Require resolvable matched_signal and recency within ``max_age_days``."""
    ref = now or datetime.now(timezone.utc)
    try:
        matched_signal(candidate, criteria, now=ref)
    except MatchedSignalError:
        return False
    activity_days = _parse_activity_days(candidate)
    if activity_days is not None:
        return activity_days <= max_age_days
    collected = candidate.collected_at
    if collected is not None:
        if collected.tzinfo is None:
            collected = collected.replace(tzinfo=timezone.utc)
        age_days = (ref - collected.astimezone(timezone.utc)).days
        return age_days <= max_age_days
    return False


def linkedin_candidate_eligible(
    candidate: Candidate,
    criteria: Sequence[Criteria],
    *,
    now: datetime | None = None,
    max_age_days: int = DEFAULT_MATCHED_SIGNAL_MAX_AGE_DAYS,
) -> bool:
    return matched_signal_is_recent(
        candidate, criteria, now=now, max_age_days=max_age_days
    )


@dataclass
class LinkedInTransport:
    """One ``send()`` records a LinkedIn message (manual delivery path)."""

    provider: LinkedInProvider
    from_profile: str = ""

    def send(
        self,
        channel: str,
        recipient: str,
        body: str,
        *,
        candidate_id: str,
    ) -> str:
        if channel != SECOND_CHANNEL:
            msg = f"LinkedInTransport only supports {SECOND_CHANNEL!r}, got {channel!r}"
            raise ValueError(msg)
        if not body.strip():
            raise LinkedInDeliveryError("empty body")
        try:
            return self.provider.send_message(
                recipient,
                body,
                candidate_id=candidate_id,
            )
        except LinkedInDeliveryError:
            raise
        except Exception as exc:
            raise LinkedInDeliveryError(str(exc)) from exc


def linkedin_provider_from_env() -> LinkedInProvider:
    token = os.environ.get("LINKEDIN_ACCESS_TOKEN", "").strip()
    if not token:
        raise LinkedInConfigError("LINKEDIN_ACCESS_TOKEN is required for LinkedIn sends")
    return EnvLinkedInProvider(access_token=token)


@dataclass
class EnvLinkedInProvider:
    """Placeholder — inject a test LinkedInProvider in unit tests."""

    access_token: str

    def send_message(
        self,
        profile_url: str,
        body: str,
        *,
        candidate_id: str,
    ) -> str:
        del profile_url, body, candidate_id, self
        raise LinkedInConfigError(
            "EnvLinkedInProvider requires live API; inject a test LinkedInProvider"
        )