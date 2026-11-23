"""Email delivery via ESP (SendGrid or SES); secrets from environment only."""

from __future__ import annotations

import html
import os
from dataclasses import dataclass
from typing import Protocol


class EmailConfigError(RuntimeError):
    """Missing or invalid email provider configuration."""


class EmailDeliveryError(RuntimeError):
    """Provider rejected or failed the send (bounce)."""

    hard: bool = True


class EmailHardBounceError(EmailDeliveryError):
    """Permanent mailbox/domain failure."""

    hard = True


class EmailSoftBounceError(EmailDeliveryError):
    """Transient failure; retry once, then count toward suppression."""

    hard = False


LIST_UNSUBSCRIBE_HEADER = "List-Unsubscribe"


def build_compliance_footer(
    *,
    sender_identity: str,
    physical_address: str,
    unsubscribe_url: str,
) -> str:
    lines = [
        "",
        "--",
        f"Sender: {sender_identity}",
        physical_address.strip(),
        "",
        "To stop receiving these emails, reply with UNSUBSCRIBE or visit:",
        unsubscribe_url.strip(),
    ]
    return "\n".join(lines)


def plain_to_html(body_plain: str) -> str:
    """Minimal HTML: escaped text in paragraphs, no images."""
    escaped = html.escape(body_plain)
    paragraphs = escaped.replace("\n\n", "</p><p>").replace("\n", "<br>\n")
    return f"<html><body><p>{paragraphs}</p></body></html>"


def maybe_tracking_pixel(body_html: str, *, enabled: bool, pixel_url: str) -> str:
    if not enabled or not pixel_url.strip():
        return body_html
    pixel = (
        f'<img src="{html.escape(pixel_url.strip())}" alt="" '
        'width="1" height="1" style="display:none" />'
    )
    if "</body>" in body_html:
        return body_html.replace("</body>", f"{pixel}</body>")
    return body_html + pixel


class EmailProvider(Protocol):
    """Injectable ESP client (real or fake in tests)."""

    def send_email(
        self,
        to: str,
        subject: str,
        body_plain: str,
        *,
        body_html: str | None = None,
        headers: dict[str, str],
    ) -> str:
        """Send multipart plain+HTML email; return provider message id."""


@dataclass
class EmailTransport:
    """One transport.send() == one ESP email with compliance footers/headers."""

    provider: EmailProvider
    from_address: str
    unsubscribe_url: str
    subject_prefix: str = "Winnow"
    sender_identity: str = ""
    physical_address: str = ""
    tracking_pixel_enabled: bool = False
    tracking_pixel_url: str = ""

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
        identity = self.sender_identity.strip() or self.from_address
        footer = build_compliance_footer(
            sender_identity=identity,
            physical_address=self.physical_address or "(address not configured)",
            unsubscribe_url=self.unsubscribe_url,
        )
        full_plain = body.rstrip() + footer
        full_html = maybe_tracking_pixel(
            plain_to_html(full_plain),
            enabled=self.tracking_pixel_enabled,
            pixel_url=self.tracking_pixel_url,
        )
        unsubscribe = self.unsubscribe_url.format(candidate_id=candidate_id)
        headers = {
            LIST_UNSUBSCRIBE_HEADER: f"<{unsubscribe}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        }
        subject = f"{self.subject_prefix}: outreach to {candidate_id}"
        try:
            return self.provider.send_email(
                recipient,
                subject,
                full_plain,
                body_html=full_html,
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
        body_plain: str,
        *,
        body_html: str | None = None,
        headers: dict[str, str],
    ) -> str:
        del headers, subject, body_plain, body_html, to
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
        body_plain: str,
        *,
        body_html: str | None = None,
        headers: dict[str, str],
    ) -> str:
        del headers, subject, body_plain, body_html, to, self
        raise EmailConfigError(
            "SesProvider requires live AWS API; inject a test EmailProvider in unit tests"
        )