"""Hard/soft bounce handling with store-backed attempt counts."""

from __future__ import annotations

from typing import TYPE_CHECKING

from winnow.outreach.transport_email import EmailDeliveryError, EmailHardBounceError

if TYPE_CHECKING:
    from winnow.outreach.suppression import SuppressionStore
    from winnow.outreach.tracker import OutreachTracker
    from winnow.store import WinnowStore

MAX_SOFT_BOUNCE_ATTEMPTS = 3


class BounceHandler:
    """Map provider bounces to status=bounced and permanent suppression."""

    def __init__(
        self,
        *,
        store: WinnowStore | None = None,
        suppression: SuppressionStore | None = None,
        tracker: OutreachTracker | None = None,
        max_soft_attempts: int = MAX_SOFT_BOUNCE_ATTEMPTS,
    ) -> None:
        self._store = store
        self._suppression = suppression
        self._tracker = tracker
        self._max_soft = max_soft_attempts

    def classify(self, exc: Exception) -> str:
        if isinstance(exc, EmailHardBounceError):
            return "hard"
        if isinstance(exc, EmailDeliveryError) and not getattr(exc, "hard", True):
            return "soft"
        return "hard"

    def handle(self, candidate_id: str, *, template_version: str, exc: Exception) -> None:
        kind = self.classify(exc)
        if kind == "hard":
            self._suppress_bounced(candidate_id, template_version)
            return
        attempts = 1
        if self._store is not None:
            attempts = self._store.increment_bounce_attempts(candidate_id)
        if attempts >= self._max_soft:
            self._suppress_bounced(candidate_id, template_version)
        elif self._tracker is not None:
            self._tracker.record_bounced(
                candidate_id, template_version=template_version
            )

    def _suppress_bounced(self, candidate_id: str, template_version: str) -> None:
        if self._store is not None:
            self._store.set_candidate_status(candidate_id, "bounced")
        if self._suppression is not None:
            self._suppression.mark_bounced(candidate_id)
        if self._tracker is not None:
            self._tracker.record_bounced(
                candidate_id, template_version=template_version
            )