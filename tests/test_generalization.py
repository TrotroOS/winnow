from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

from winnow.models import Criteria, StartupSituation
from winnow.router import route
from winnow.run import execute, register_sources_from_config
from winnow.sources.csv_fixture import CsvFixtureSource
from winnow.sources.mock import MockSource
from winnow.sources.registry import clear, register

REPO_ROOT = Path(__file__).resolve().parents[1]

_CORE_LOCK = {
    "filter.py": "5f0a3763ef08c386a3a90776c09676063a4cb00f7b9e23db42ae4da72b65566e",
    "enrich.py": "8e739fa4cf28a45c50408edde5653215adbf7523af6b50dcc736ea05eed17a0b",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_filter_and_enrich_unmodified_vs_merge_base() -> None:
    merge = subprocess.run(
        ["git", "merge-base", "origin/main", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    base = merge.stdout.strip()
    diff = subprocess.run(
        [
            "git",
            "diff",
            base,
            "--",
            "src/winnow/filter.py",
            "src/winnow/enrich.py",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    working = subprocess.run(
        ["git", "diff", "HEAD", "--", "src/winnow/filter.py", "src/winnow/enrich.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert diff.stdout.strip() == "" or working.stdout.strip() == "", (
        "filter.py and enrich.py must stay untouched by generalization:\n"
        + (diff.stdout or working.stdout)
    )
    enrich = REPO_ROOT / "src" / "winnow" / "enrich.py"
    filt = REPO_ROOT / "src" / "winnow" / "filter.py"
    assert _sha256(filt) == _CORE_LOCK["filter.py"]
    assert _sha256(enrich) == _CORE_LOCK["enrich.py"]


def test_router_orders_cheapest_mock_then_csv() -> None:
    clear()
    register(MockSource())
    register(CsvFixtureSource())
    criteria = [
        Criteria(name="always", predicate=lambda _: True, cost=0),
    ]
    situation = StartupSituation(
        stage="growth",
        product="Winnow",
        goal="segment expansion",
        constraint="budget",
        segment="enterprise",
    )
    ordered = route(situation, criteria)
    assert [a.name for a in ordered] == ["mock", "csv_fixture"]
    assert [a.cost_per_call for a in ordered] == [0.0, 0.01]


def test_community_config_e2e_dry_run(tmp_path: Path) -> None:
    config = REPO_ROOT / "config_community.yaml"
    result, summary = execute(config, dry_run=True, limit=50, logs_dir=tmp_path / "logs")
    assert result.situation_type == "community"
    assert "template: community" in summary
    assert result.spend_this_run == 0.0


def test_segment_expansion_config_e2e_dry_run(tmp_path: Path) -> None:
    config = REPO_ROOT / "config_segment_expansion.yaml"
    result, summary = execute(config, dry_run=True, limit=50, logs_dir=tmp_path / "logs")
    assert result.situation_type == "segment_expansion"
    assert "template: segment_expansion" in summary
    assert "mock" in result.sources
    assert "csv_fixture" in result.sources
    assert len(result.possible) >= 1
    assert result.spend_this_run == 0.0


def test_register_sources_from_yaml_lists(tmp_path: Path) -> None:
    import yaml

    raw = yaml.safe_load(
        (REPO_ROOT / "config_segment_expansion.yaml").read_text(encoding="utf-8")
    )
    register_sources_from_config(raw)
    from winnow.sources.registry import list_adapters

    names = {a.name for a in list_adapters()}
    assert names == {"mock", "csv_fixture"}