"""Runtime configuration from environment variables — no hardcoded secrets."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _optional_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return int(raw)


@dataclass(frozen=True)
class WinnowConfig:
    """Secrets and limits loaded from the environment."""

    spend_cap_cents: int
    enrichment_api_key: str | None
    csv_source_dir: str | None
    github_token: str | None

    @classmethod
    def from_env(cls) -> WinnowConfig:
        return cls(
            spend_cap_cents=_optional_int("WINNOW_SPEND_CAP_CENTS", 0),
            enrichment_api_key=os.environ.get("WINNOW_ENRICHMENT_API_KEY"),
            csv_source_dir=os.environ.get("WINNOW_CSV_SOURCE_DIR"),
            github_token=os.environ.get("WINNOW_GITHUB_TOKEN"),
        )