"""Adapter volume controls: concurrency, quota, and same-day response cache."""

from __future__ import annotations

import logging
import threading
from collections.abc import Sequence
from dataclasses import dataclass, field

from winnow.models import Candidate
from winnow.sources.adapter import SourceAdapter
from winnow.store import WinnowStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AdapterVolumeSpec:
    concurrency: int = 1
    quota_per_run: int | None = None
    quota_per_day: int | None = None


def parse_adapter_volume_config(
    raw: dict | None,
    *,
    default_concurrency: int = 1,
) -> dict[str, AdapterVolumeSpec]:
    """Parse ``adapter_volume`` mapping from YAML config."""
    if not raw or not isinstance(raw, dict):
        return {}
    default_raw = raw.get("default")
    default_conc = default_concurrency
    if isinstance(default_raw, dict) and default_raw.get("concurrency") is not None:
        default_conc = int(default_raw["concurrency"])
    specs: dict[str, AdapterVolumeSpec] = {}
    for name, body in raw.items():
        if name == "default" or not isinstance(body, dict):
            continue
        conc = int(body.get("concurrency", default_conc))
        per_run = body.get("quota_per_run")
        per_day = body.get("quota_per_day")
        specs[name] = AdapterVolumeSpec(
            concurrency=max(1, conc),
            quota_per_run=int(per_run) if per_run is not None else None,
            quota_per_day=int(per_day) if per_day is not None else None,
        )
    return specs


def spec_for_adapter(
    name: str,
    specs: dict[str, AdapterVolumeSpec],
    *,
    default_concurrency: int = 1,
) -> AdapterVolumeSpec:
    return specs.get(
        name,
        AdapterVolumeSpec(concurrency=max(1, default_concurrency)),
    )


def query_cache_key(queries: list[str]) -> str:
    return "|".join(q.strip() for q in queries if q and str(q).strip())


def _serialize_search_item(item: Candidate | dict[str, object]) -> dict[str, object]:
    if isinstance(item, Candidate):
        return {
            "_kind": "candidate",
            "id": item.id,
            "name": item.name,
            "org": item.org,
            "role": item.role,
            "signals": dict(item.signals),
            "contacts": dict(item.contacts),
            "source": item.source,
            "collected_at": item.collected_at.isoformat(),
        }
    return {"_kind": "raw", "data": dict(item)}


def _deserialize_search_item(row: dict[str, object]) -> Candidate | dict[str, object]:
    kind = row.get("_kind")
    if kind == "candidate":
        collected_raw = str(row.get("collected_at", ""))
        try:
            from datetime import datetime

            collected_at = datetime.fromisoformat(collected_raw)
        except ValueError:
            from datetime import datetime, timezone

            collected_at = datetime.now(timezone.utc)
        return Candidate(
            id=str(row.get("id", "")),
            name=str(row.get("name", "")),
            org=str(row.get("org", "")),
            role=str(row.get("role", "")),
            signals={str(k): str(v) for k, v in dict(row.get("signals", {})).items()},
            contacts={str(k): str(v) for k, v in dict(row.get("contacts", {})).items()},
            source=str(row.get("source", "")),
            collected_at=collected_at,
        )
    if kind == "raw":
        data = row.get("data")
        if isinstance(data, dict):
            return dict(data)
    return dict(row)


@dataclass
class VolumeWrappedAdapter:
    """Concurrency, quota, and cache around a source adapter (read-only for filter)."""

    inner: SourceAdapter
    store: WinnowStore
    spec: AdapterVolumeSpec
    day: str
    run_key: str
    _semaphore: threading.Semaphore = field(init=False)
    quota_hits: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self._semaphore = threading.Semaphore(self.spec.concurrency)

    @property
    def name(self) -> str:
        return self.inner.name

    @property
    def cost_per_call(self) -> float:
        return float(self.inner.cost_per_call)

    def search(self, queries: list[str], limit: int) -> list[Candidate]:
        with self._semaphore:
            allowed, reason = self.store.quota_allows(
                self.name,
                day=self.day,
                run_key=self.run_key,
                per_run=self.spec.quota_per_run,
                per_day=self.spec.quota_per_day,
            )
            if not allowed:
                self.quota_hits += 1
                logger.warning("%s", reason)
                return []

            key = query_cache_key(queries)
            cached = self.store.cache_get(self.name, key, self.day)
            if cached is not None:
                restored: list[Candidate] = []
                for row in cached:
                    item = _deserialize_search_item(row)
                    if isinstance(item, Candidate):
                        restored.append(item)
                    else:
                        from winnow.normalize import normalize

                        restored.append(normalize(item, self.name))
                return restored[: max(0, limit)]

            raw = self.inner.search(queries, limit)
            payload = [_serialize_search_item(item) for item in raw]
            self.store.cache_put(self.name, key, self.day, payload)
            self.store.record_adapter_call(self.name, day=self.day, run_key=self.run_key)
            return raw


def wrap_adapters(
    adapters: Sequence[SourceAdapter],
    *,
    store: WinnowStore,
    specs: dict[str, AdapterVolumeSpec],
    day: str,
    run_key: str,
    default_concurrency: int = 1,
) -> list[VolumeWrappedAdapter]:
    return [
        VolumeWrappedAdapter(
            inner=adapter,
            store=store,
            spec=spec_for_adapter(adapter.name, specs, default_concurrency=default_concurrency),
            day=day,
            run_key=run_key,
        )
        for adapter in adapters
    ]