"""Route transport.send() to the channel-specific implementation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class Transport(Protocol):
    def send(
        self,
        channel: str,
        recipient: str,
        body: str,
        *,
        candidate_id: str,
    ) -> str: ...


@dataclass
class ChannelRouterTransport:
    """Delegate sends to email and/or LinkedIn transports by ``channel``."""

    email: Transport | None = None
    linkedin: Transport | None = None

    def send(
        self,
        channel: str,
        recipient: str,
        body: str,
        *,
        candidate_id: str,
    ) -> str:
        if channel == "email":
            if self.email is None:
                raise ValueError("no email transport configured")
            return self.email.send(
                channel, recipient, body, candidate_id=candidate_id
            )
        if channel == "linkedin":
            if self.linkedin is None:
                raise ValueError("no linkedin transport configured")
            return self.linkedin.send(
                channel, recipient, body, candidate_id=candidate_id
            )
        raise ValueError(f"unsupported channel {channel!r}")