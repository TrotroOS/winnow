"""Email delivery via ESP (SendGrid or SES); secrets from environment only."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol


class EmailConfigError(RuntimeError):
    """Missing or invalid email provider configuration."""


class EmailDeliveryError(RuntimeError):
    """Provider rejected or failed the send (bounce)."""


OPT_OUT_LINE = (
    "\n\n--\nTo stop receiving these emails, reply with UNSUBSCRIBE "
    "or use the link in List-Unsubscribe."
)

LIST_UNSUBSCRIBE_HEADER = "List-Unsubscribe"


class EmailProvider(Protocol):
    """Injectable ESP client (real or fake in tests)."""

    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        *,
        headers: dict[str, str],
    ) -> str:
        """Send plain-text email; return provider message id."""


@dataclass
class EmailTransport:
    """One transport.send() == one ESP email with compliance footers/headers."""

    provider: EmailProvider
    from_address: str
    unsubscribe_url: str
    subject_prefix: str = "Winnow"

    def send(
        self,
        channel: str,
        recipient: str,
        body: str,
        *,
        candidate_id: str,
    ) -> str:
        if channel != "email":
            msg = f"EmailTransport only supports email, got {channel!r}"
            raise ValueError(msg)
        full_body = body.rstrip() + OPT_OUT_LINE
        headers = {
            LIST_UNSUBSCRIBE_HEADER: f"<{self.unsubscribe_url}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        }
        subject = f"{self.subject_prefix}: outreach to {candidate_id}"
        try:
            return self.provider.send_email(
                recipient,
                subject,
                full_body,
                headers=headers,
            )
        except EmailDeliveryError:
            raise
        except Exception as exc:
            raise EmailDeliveryError(str(exc)) from exc


def email_provider_from_env() -> EmailProvider:
    """Build ESP client from ``WINNOW_EMAIL_PROVIDER`` and provider API keys."""
    name = os.environ.get("WINNOW_EMAIL_PROVIDER", "").strip().lower()
    if not name:
        raise EmailConfigError(
            "WINNOW_EMAIL_PROVIDER is required (sendgrid or ses)"
        )
    if name == "sendgrid":
        api_key = os.environ.get("SENDGRID_API_KEY", "").strip()
        if not api_key:
            raise EmailConfigError("SENDGRID_API_KEY is required for sendgrid")
        return SendGridProvider(api_key=api_key)
    if name in {"ses", "aws_ses"}:
        access_key = os.environ.get("AWS_ACCESS_KEY_ID", "").strip()
        secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY", "").strip()
        region = os.environ.get("AWS_REGION", os.environ.get("SES_REGION", "us-east-1"))
        if not access_key or not secret_key:
            raise EmailConfigError(
                "AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY required for ses"
            )
        return SesProvider(
            access_key_id=access_key,
            secret_access_key=secret_key,
            region=region,
        )
    raise EmailConfigError(f"unknown WINNOW_EMAIL_PROVIDER {name!r}")


@dataclass
class SendGridProvider:
    """SendGrid HTTP API (no SDK — minimal POST for production wiring)."""

    api_key: str

    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        *,
        headers: dict[str, str],
    ) -> str:
        del headers, subject, body, to
        raise EmailConfigError(
            "SendGridProvider requires live HTTP; inject a test EmailProvider in unit tests"
        )


@dataclass
class SesProvider:
    """Amazon SES placeholder — inject client in integration tests."""

    access_key_id: str
    secret_access_key: str
    region: str

    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        *,
        headers: dict[str, str],
    ) -> str:
        del headers, subject, body, to, self
        raise EmailConfigError(
            "SesProvider requires live AWS API; inject a test EmailProvider in unit tests"
        )