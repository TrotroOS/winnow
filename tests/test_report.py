from __future__ import annotations

import re
from datetime import datetime, timezone
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from winnow.report import (
    format_prometheus,
    load_run_report,
    main,
    metrics_enabled,
)
from winnow.models import Candidate
from winnow.store import WinnowStore


def _candidate(cid: str) -> Candidate:
    return Candidate(
        id=cid,
        name=cid,
        org="Org",
        role="Member",
        signals={},
        contacts={"email": f"{cid}@example.com"},
        source="mock",
        collected_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _seed_run(
    store: WinnowStore,
    *,
    run_key: str = "rk-1",
) -> int:
    crit_id = store.record_criteria_version(
        "community",
        ("community_member", "recent_activity"),
    )
    situation = {
        "stage": "seed",
        "product": "Winnow",
        "goal": "grow",
        "segment": "devtools",
    }
    sources = ["mock", "paid_spy"]
    outreach = {"sent": 10, "replied": 2, "bounced": 1, "suppressed": 0, "skipped": 0}
    run_id = store.record_run(
        criteria_version_id=crit_id,
        situation_type="community",
        possible_count=5,
        noise_dropped=3,
        spend_run=2.5,
        enriched_count=4,
        backlog_count=1,
        sources=sources,
        situation=situation,
        run_key=run_key,
        outreach=outreach,
    )
    store.record_adapter_call("mock", day="2026-11-23", run_key=run_key)
    store.record_adapter_call("mock", day="2026-11-23", run_key=run_key)
    store.record_adapter_call("paid_spy", day="2026-11-23", run_key=run_key)
    for cid in ("c1", "c2", "c3"):
        store.save_candidate(_candidate(cid), "possible")
    store.record_send(
        candidate_id="c1",
        run_id=run_id,
        channel="email",
        template_version="community",
        status="sent",
    )
    store.record_send(
        candidate_id="c2",
        run_id=run_id,
        channel="email",
        template_version="community",
        status="replied",
    )
    store.record_send(
        candidate_id="c3",
        run_id=run_id,
        channel="linkedin",
        template_version="community",
        status="sent",
    )
    return run_id


def test_report_text_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "winnow.sqlite"
    monkeypatch.setenv("WINNOW_DB_PATH", str(db))
    store = WinnowStore(db)
    run_id = _seed_run(store)
    store.close()

    store2 = WinnowStore(db)
    report = load_run_report(store2, run_id)
    store2.close()

    assert report.template == "community"
    assert report.possible == 5
    assert report.enriched == 4
    assert report.backlog == 1
    assert report.sends_by_channel == {"email": 2, "linkedin": 1}
    assert "score" not in format_prometheus(report).lower()


def test_cli_run_last_and_html(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logs = tmp_path / "logs"
    db = logs / "winnow.sqlite"
    monkeypatch.setenv("WINNOW_DB_PATH", str(db))
    store = WinnowStore(db)
    first = _seed_run(store, run_key="a")
    _seed_run(store, run_key="b")
    store.close()

    code = main(["--run", str(first), "--last", "2", "--html", "--logs-dir", str(logs)])
    assert code == 0
    out = capsys.readouterr().out
    assert "run_id |" in out
    assert f"run_id: {first}" in out
    assert "criteria_names:" in out
    assert "bounce_rate:" in out
    assert "score" not in out.lower()

    html_paths = list(logs.glob("report_*.html"))
    assert len(html_paths) == 1
    body = html_paths[0].read_text(encoding="utf-8")
    assert "http://" not in body and "https://" not in body
    assert "<style>" in body


def test_metrics_endpoint_when_enabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = tmp_path / "winnow.sqlite"
    monkeypatch.setenv("WINNOW_DB_PATH", str(db))
    monkeypatch.setenv("WINNOW_METRICS", "1")
    monkeypatch.setenv("WINNOW_METRICS_PORT", "59101")
    store = WinnowStore(db)
    run_id = _seed_run(store)
    store.close()

    assert metrics_enabled()
    code = main(["--run", str(run_id)])
    assert code == 0

    url = "http://127.0.0.1:59101/metrics"
    last_err: Exception | None = None
    for _ in range(20):
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                text = resp.read().decode("utf-8")
            break
        except (urllib.error.URLError, TimeoutError) as exc:
            last_err = exc
    else:
        raise AssertionError(f"metrics server unavailable: {last_err}")

    assert re.search(r'winnow_run_possible\{run_id="' + str(run_id), text)
    assert "winnow_run_reply_rate" in text
    assert "score" not in text.lower()