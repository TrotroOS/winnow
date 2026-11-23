from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from winnow.models import Candidate, Criteria
from winnow import enrich as enrich_module
from winnow.orchestrator import RunConfig, run
from winnow.sources.registry import clear, register
from winnow.sources.volume import AdapterVolumeSpec, VolumeWrappedAdapter, wrap_adapters
from winnow.store import WinnowStore

REPO_ROOT = Path(__file__).resolve().parents[1]

_CORE_LOCK = {
    "filter.py": "5f0a3763ef08c386a3a90776c09676063a4cb00f7b9e23db42ae4da72b65566e",
    "enrich.py": "8e739fa4cf28a45c50408edde5653215adbf7523af6b50dcc736ea05eed17a0b",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_filter_and_enrich_unmodified_like_generalization() -> None:
    diff = subprocess.run(
        ["git", "diff", "HEAD", "--", "src/winnow/filter.py", "src/winnow/enrich.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert diff.stdout.strip() == "", diff.stdout
    assert _sha256(REPO_ROOT / "src/winnow/filter.py") == _CORE_LOCK["filter.py"]
    assert _sha256(REPO_ROOT / "src/winnow/enrich.py") == _CORE_LOCK["enrich.py"]


@dataclass
class CountingAdapter:
    name: str = "counter"
    cost_per_call: float = 0.0
    calls: int = field(default=0, init=False)
    rows: list[Candidate] = field(default_factory=list)

    def search(self, queries: list[str], limit: int) -> list[Candidate]:
        del queries
        self.calls += 1
        return self.rows[:limit]


@dataclass
class PaidCounter:
    name: str = "paid_counter"
    cost_per_call: float = 1.0
    calls: int = field(default=0, init=False)
    order: list[str] = field(default_factory=list)

    def search(self, queries: list[str], limit: int) -> list[Candidate]:
        del queries, limit
        self.calls += 1
        tag = f"call-{self.calls}"
        self.order.append(tag)
        return [
            Candidate(
                id=f"paid-{tag}",
                name="Paid",
                org="Org",
                role="R",
                signals={"community_member": "yes", "activity_days": "2"},
                contacts={"email": f"p-{tag}@example.com"},
                source=self.name,
                collected_at=datetime(2026, 11, 23, tzinfo=timezone.utc),
            )
        ]


def _community_row(cid: str) -> Candidate:
    return Candidate(
        id=cid,
        name=f"User {cid}",
        org="Dev Club",
        role="Member",
        signals={"community_member": "yes", "activity_days": "2"},
        contacts={"email": f"{cid}@example.com"},
        source="counter",
        collected_at=datetime(2026, 11, 23, tzinfo=timezone.utc),
    )


def test_quota_blocks_before_inner_call(tmp_path: Path) -> None:
    store = WinnowStore(tmp_path / "winnow.sqlite")
    inner = CountingAdapter(rows=[_community_row("a")])
    wrapped = wrap_adapters(
        [inner],
        store=store,
        specs={
            "counter": AdapterVolumeSpec(quota_per_run=1, quota_per_day=10),
        },
        day="2026-11-23",
        run_key="run-1",
    )[0]
    first = wrapped.search(["q"], 10)
    second = wrapped.search(["q"], 10)
    assert len(first) == 1
    assert second == []
    assert inner.calls == 1
    assert wrapped.quota_hits == 1


def test_cache_hit_zero_adapter_calls_on_second_same_day_run(tmp_path: Path) -> None:
    store = WinnowStore(tmp_path / "winnow.sqlite")
    inner = CountingAdapter(rows=[_community_row("cache-1")])
    spec = { "counter": AdapterVolumeSpec() }
    day = "2026-11-23"
    wrap_adapters([inner], store=store, specs=spec, day=day, run_key="r1")[0].search(
        ["devtools"], 5
    )
    assert inner.calls == 1
    inner.calls = 0
    wrap_adapters([inner], store=store, specs=spec, day=day, run_key="r2")[0].search(
        ["devtools"], 5
    )
    assert inner.calls == 0


def test_backlog_drains_before_new_collection(tmp_path: Path) -> None:
    store = WinnowStore(tmp_path / "winnow.sqlite")
    backlog_row = _community_row("backlog-seed")
    store.save_candidate(backlog_row, "possible", backlog=True)

    paid = PaidCounter()
    clear()
    register(CountingAdapter(rows=[_community_row("new-collect")]))
    register(paid)

    situation = {
        "situation_type": "community",
        "stage": "seed",
        "product": "Winnow",
        "goal": "grow community",
        "constraint": "time",
        "segment": "devtools",
        "channels": ("email",),
    }
    cfg = RunConfig(
        max_spend_per_run=10.0,
        max_spend_per_month=100.0,
        store=store,
        search_limit=5,
        enrich_limit=5,
        volume_day="2026-11-23",
        adapter_volume={"paid_counter": AdapterVolumeSpec(quota_per_run=100)},
    )
    enrich_batches: list[tuple[str, ...]] = []

    def _spy_enrich(possible, *args, **kwargs):
        enrich_batches.append(tuple(c.id for c in possible))
        return enrich_module.enrich(possible, *args, **kwargs)

    with patch("winnow.orchestrator.enrich", side_effect=_spy_enrich):
        run(situation, cfg)
    assert enrich_batches[0] == ("backlog-seed",)
    assert enrich_batches[1] == ("new-collect",)


def test_filter_still_runs_with_cached_rows(tmp_path: Path) -> None:
    store = WinnowStore(tmp_path / "winnow.sqlite")
    noise_row = Candidate(
        id="noise-x",
        name="Noise",
        org="Dev Club",
        role="Member",
        signals={},
        contacts={"email": "noise@example.com"},
        source="counter",
        collected_at=datetime(2026, 11, 23, tzinfo=timezone.utc),
    )
    inner = CountingAdapter(rows=[noise_row])
    wrapped = VolumeWrappedAdapter(
        inner=inner,
        store=store,
        spec=AdapterVolumeSpec(),
        day="2026-11-23",
        run_key="rk",
    )
    wrapped.search(["q"], 5)
    inner.rows = [_community_row("fresh")]
    second = wrapped.search(["q"], 5)
    assert second[0].id == "noise-x"
    assert inner.calls == 1