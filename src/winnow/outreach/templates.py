"""Outreach message bodies per situation type."""

from __future__ import annotations

from collections.abc import Sequence

from winnow.models import Candidate, Criteria
from winnow.outreach.personalize import matched_signal

TEMPLATE_VERSION = "2026.11"

MESSAGE_TEMPLATES: dict[str, str] = {
    "design_partners": (
        "Hi {name},\n\n"
        "I noticed {matched_signal} at {org}. "
        "We're looking for design partners — open to a short chat?"
    ),
    "first_revenue": (
        "Hi {name},\n\n"
        "At {org}, {matched_signal} caught my eye. "
        "Would you be open to seeing how we might help you ship faster?"
    ),
    "distribution_partners": (
        "Hi {name},\n\n"
        "{org} — {matched_signal}. "
        "We're exploring distribution partners; worth a quick connect?"
    ),
    "investors": (
        "Hi {name},\n\n"
        "Given {matched_signal} at {org}, I'd love to share what we're building."
    ),
    "hires": (
        "Hi {name},\n\n"
        "Saw that {org} — {matched_signal}. "
        "We help teams like yours find the right candidates; open to intros?"
    ),
    "community": (
        "Hi {name},\n\n"
        "Noticed {matched_signal} at {org}. "
        "We'd love your perspective as we grow the community."
    ),
}


def build_message(
    situation_type: str,
    candidate: Candidate,
    criteria: Sequence[Criteria],
) -> str:
    """Format the outreach body; raises if ``matched_signal`` cannot be determined."""
    key = situation_type.strip().lower()
    try:
        template = MESSAGE_TEMPLATES[key]
    except KeyError as exc:
        known = ", ".join(sorted(MESSAGE_TEMPLATES))
        raise ValueError(f"Unknown situation {situation_type!r}; known: {known}") from exc
    hook = matched_signal(candidate, criteria)
    return template.format(
        name=candidate.name or "there",
        org=candidate.org or "your team",
        matched_signal=hook,
    )