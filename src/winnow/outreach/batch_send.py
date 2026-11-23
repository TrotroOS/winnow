"""Load staged batch JSON and deliver after explicit confirmation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from winnow.models import OutreachSummary
from winnow.outreach.sender import OutboundMessage, OutreachSender, SendBatch
from winnow.outreach.suppression import SuppressionStore
from winnow.outreach.domain_throttle import RecipientDomainThrottle
from winnow.outreach.throttle import Throttle
from winnow.outreach.tracker import OutreachTracker
from winnow.outreach.guards import sends_halted
from winnow.outreach.routing_transport import ChannelRouterTransport
from winnow.outreach.transport_email import (
    EmailProvider,
    EmailTransport,
    email_provider_from_env,
)
from winnow.outreach.transport_linkedin import (
    DEFAULT_LINKEDIN_DAILY_CAP,
    LinkedInProvider,
    LinkedInTransport,
    linkedin_provider_from_env,
)
from winnow.outreach.warmup import effective_daily_cap


@dataclass
class SendBatchConfig:
    daily_cap: int = 25
    per_run_send_cap: int = 25
    warmup_start_daily_cap: int = 5
    warmup_step: int = 5
    warmup_start_date: str | None = None
    from_address: str = "outreach@example.com"
    unsubscribe_url: str = "https://example.com/unsubscribe?c={candidate_id}"
    sender_identity: str = ""
    physical_address: str = ""
    tracking_pixel_enabled: bool = False
    tracking_pixel_url: str = ""
    max_per_hour_per_recipient_domain: int = 20
    throttle_day: date | None = None
    linkedin_daily_cap: int = DEFAULT_LINKEDIN_DAILY_CAP


def load_batch_file(path: Path) -> SendBatch:
    raw = json.loads(path.read_text(encoding="utf-8"))
    messages = [
        OutboundMessage(**row) for row in raw.get("messages", [])
    ]
    return SendBatch(batch_id=str(raw.get("batch_id", "unknown")), messages=messages)


def send_batch(
    path: Path,
    *,
    confirm: bool,
    config: SendBatchConfig,
    provider: EmailProvider | None = None,
    linkedin_provider: LinkedInProvider | None = None,
    transport: ChannelRouterTransport | EmailTransport | None = None,
) -> OutreachSummary:
    """Deliver a staged batch. Without ``confirm``, returns zeros and sends nothing."""
    if not confirm:
        return OutreachSummary()

    if sends_halted():
        batch = load_batch_file(path)
        return OutreachSummary(skipped=len(batch.messages))

    cap = effective_daily_cap(
        ceiling=config.daily_cap,
        warmup_start_daily_cap=config.warmup_start_daily_cap,
        warmup_step=config.warmup_step,
        warmup_start_date=config.warmup_start_date,
        today=config.throttle_day,
    )
    throttle = Throttle(
        caps={
            "email": cap,
            "linkedin": config.linkedin_daily_cap,
            "dm": 0,
        },
        day=config.throttle_day,
    )
    if transport is None:
        esp = provider or email_provider_from_env()
        email_t = EmailTransport(
            provider=esp,
            from_address=config.from_address,
            unsubscribe_url=config.unsubscribe_url,
            sender_identity=config.sender_identity or config.from_address,
            physical_address=config.physical_address,
            tracking_pixel_enabled=config.tracking_pixel_enabled,
            tracking_pixel_url=config.tracking_pixel_url,
        )
        router = ChannelRouterTransport(email=email_t)
        batch_preview = load_batch_file(path)
        if any(m.channel == "linkedin" for m in batch_preview.messages):
            li_provider = linkedin_provider or linkedin_provider_from_env()
            router.linkedin = LinkedInTransport(provider=li_provider)
        transport = router

    batch = load_batch_file(path)
    domain_throttle = RecipientDomainThrottle(
        max_per_hour=config.max_per_hour_per_recipient_domain,
    )
    sender = OutreachSender(
        transport=transport,
        suppression=SuppressionStore(),
        throttle=throttle,
        tracker=OutreachTracker(),
        per_run_send_cap=config.per_run_send_cap,
        domain_throttle=domain_throttle,
    )
    return sender.deliver_batch(batch)