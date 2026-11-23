# Winnow RUNBOOK

## What Winnow is

Winnow finds the people a startup must reach for its current situation, filters them with **binary-only** rules, enriches and outreaches in budget, and logs everything. A candidate is **POSSIBLE** or **NOISE** — no third state. Every criterion is a pure `bool` predicate; reachability is a separate hard gate (non-empty email, LinkedIn, or DM). NOISE is never stored, listed, or contacted — only a drop count is recorded. Every POSSIBLE candidate gets at most one outreach action per cycle. If you need a number that means “how good” someone is, that is a bug: tighten or loosen predicates instead.

---

## Daily loop (operator)

1. **Dry-run** — collect, filter, and account for spend without paid calls:
   ```bash
   pip install -e ".[dev]"
   python -m winnow.run --config config_community.yaml --limit 50 --dry-run
   ```
   Review the printed summary: `possible`, `noise_dropped`, `enriched`, `backlog`, spend.

2. **Review batch** — open `logs/batch_<timestamp>.json` from the run. Read each message body, `matched_signal`, and channel. Reject anything that feels off; do not edit criteria automatically.

3. **Confirm send** (manual mode only) — only after review:
   ```bash
   python -m winnow.run send-batch logs/batch_<timestamp>.json --confirm
   ```
   Without `--confirm`, nothing leaves the machine.

4. **Check tracker** — inspect outreach records (sent, replied, bounced, opt_out) in logs and any dashboard you maintain from `logs/runs.jsonl`.

5. **Read feedback** — suggestions print to the console and append to `logs/feedback.jsonl`. They are **human recommendations only**; never auto-applied.

**Kill switch before any live day:** if anything looks wrong, set `WINNOW_HALT=1` in the environment; all sends block immediately.

### Optional: automated daily dry-run (scheduler)

The scheduler never calls a transport. It dry-runs the pipeline, checks operator POSSIBLE bounds, writes `logs/batch_<timestamp>.json` when in range, and appends `logs/notifications.jsonl`. Set `daily_run_time` (default `09:00`) and optional `timezone` (default `UTC`) in config.

```bash
python -m winnow.run schedule --config config.yaml          # wait loop
python -m winnow.run schedule --config config.yaml --once     # run one cycle now
python -m winnow.scheduler --config config.yaml --once
```

Concurrent runs are blocked by `logs/winnow.run.lock`. If monthly budget remaining is below `max_spend_per_run`, the cycle is skipped (exit 0). `WINNOW_HALT=1` blocks the scheduler entirely.

---

## Weekly loop (operator)

1. **Tune one predicate** — pick a single `Criteria.name` from feedback (tighten or loosen one bool rule). Change templates or predicates; do not add weights or scores.

2. **Compare reply rate by template version** — use `ingest(tracker)` stats per template; compare runs that used different `TEMPLATE_VERSION` / criteria names in audit logs.

3. **Source decision** — if POSSIBLE count is too small after honest predicates, consider adding a **cheaper** source adapter (higher `cost_per_call` only after free sources are exhausted). Never bypass the filter for volume.

---

## Spend discipline

| Control | Default (see `config.yaml`) | Purpose |
|--------|------------------------------|---------|
| `max_spend_per_run` | 5 | USD (or account units) cap per pipeline run |
| `max_spend_per_month` | 100 | Monthly enrichment ceiling |
| `max_sends_per_run` | 25 | Outreach sends cap per run |
| `daily_cap` | 25 | Per-channel throttle baseline |
| Warm-up | `warmup_start_daily_cap`, `warmup_step` | Ramp domain sending |

**Where money is tracked**

- **Run spend (this run):** printed summary `spend_this_run`; audit field in `logs/runs.jsonl`.
- **Monthly persistence:** `logs/spend.json` — loaded on startup so restarts do not reset the month.

**Raising caps deliberately**

1. Edit `config.yaml` (or `config_<situation>.yaml`) — increase `max_spend_per_run` / `max_spend_per_month` / `daily_cap` in small steps.
2. Document why in your own ops log (not in repo secrets).
3. Re-run **dry-run** and confirm `backlog` and spend accounting before live enrich or send.
4. Never raise caps to “get more POSSIBLE” — fix predicates or sources instead.

Enrichment is paid; collection from `cost_per_call: 0` adapters is free. Router orders sources cheapest-first.

---

## Add a new situation template (checklist)

- [ ] Read `CLAUDE.md` binary-only rules.
- [ ] Add a function in `src/winnow/criteria/templates.py` returning `(list[Criteria], reachability)` with **named bool predicates only** (`cost` is execution order, not weighting).
- [ ] Add a matching outreach body in `src/winnow/outreach/templates.py` with `{name}`, `{org}`, `{matched_signal}`.
- [ ] Register template name in `TEMPLATES` / builder routing (`situation_type` in config).
- [ ] Add `DESCRIPTION_BY_CRITERION` entries in `personalize.py` for each criterion that can supply `matched_signal`.
- [ ] Add tests in `tests/test_criteria_builder.py`: matching candidate → POSSIBLE; non-matching → dropped.
- [ ] **Do not** modify `filter.py` or `enrich.py` unless the core contract truly changed (stop and escalate if you think you must).
- [ ] Add `config_<situation>.yaml` and run dry-run end-to-end.

---

## Add a new source adapter (checklist)

- [ ] Implement `src/winnow/sources/<name>.py`: `name`, `cost_per_call` (real list price for routing/spend only), `search(queries, limit) -> list[dict]` **raw dicts only** (normalization in `normalize.py`).
- [ ] Pagination internal; hard-stop at `limit`.
- [ ] HTTP: timeout, single retry with backoff, call counter (if applicable).
- [ ] Credentials **only** from env vars; clear error if missing.
- [ ] Register in `src/winnow/sources/registry.py`.
- [ ] Tests with recorded fixture: expected raw dict count, `limit`, missing creds, simulated 429 retry-then-fail.
- [ ] **No** code that decides if a candidate is good — that stays in the filter.
- [ ] Confirm `route()` orders your adapter vs existing ones by `cost_per_call`.

---

## Failure playbook

| Symptom | Likely cause | Action |
|--------|----------------|--------|
| **High bounce (>3%)** | Bad emails, stale data, reachability too loose | Tighten reachability or source; read feedback bounce suggestion; pause with `WINNOW_HALT=1`; do not auto_send until last 3 runs improve |
| **Zero replies** | Wrong segment/predicate, weak `matched_signal` | Review feedback; tighten segment predicate or template; A/B one predicate change per week |
| **Cap hit mid-run** | Budget or send limits | Expected: `backlog_count` / skipped in summary; raise caps only deliberately (see Spend) or reduce `limit` |
| **API 429** | Provider rate limit | Adapter retries once; back off schedule; lower `limit` and daily_cap; cheapest source first |
| **Suppression conflicts** | Re-contacting same id | Normal: skipped count increases; clear only if policy allows; never bypass suppression for volume |
| **auto_send refused at startup** | Last 3 runs: bounce >3% or zero replies | Falls back to `manual_approve` with warning — fix deliverability before re-enabling auto |

Audit trail: `logs/runs.jsonl` (full chain per run). Feedback: `logs/feedback.jsonl`.

---

## Guard prompt (copy-paste for agents and humans)

Use this before any change to Winnow logic, prompts, or operator process:

```
WINNOW GUARD — BINARY ONLY

- Candidates are POSSIBLE or NOISE only. No scores, ranks, weights, confidence, fit, top-N, or priority fields.
- Criteria are pure bool predicates. Reachability (email/linkedin/dm) is a hard gate, not a scored criterion.
- NOISE is deleted: never stored, queued, returned, or contacted. Log drop counts only.
- Enrichment (paid) runs only after apply_filter on POSSIBLE. Free sources first; router orders by cost_per_call.
- Outreach only targets POSSIBLE. One touch per candidate per cycle; suppression is mandatory.
- matched_signal is the personalization hook; if it cannot be determined, do not send (raise).
- manual_approve default: batch to logs/batch_*.json; live send only with explicit --confirm.
- WINNOW_HALT=1 blocks all sends. auto_send is bounded by daily_cap, max_sends_per_run, spend caps, and recent bounce/reply guard.
- Tuning is human: add/remove/tighten predicates or sources. Feedback suggestions are never auto-applied.
- If you are about to add a number that means "how good" a candidate is, STOP — that is a bug.
```

---

## Quick reference commands

```bash
# Dry-run (safe default)
python -m winnow.run --config config_community.yaml --limit 50 --dry-run

# Alternate situation config
python -m winnow.run --config config_segment_expansion.yaml --limit 50 --dry-run

# Send reviewed batch
python -m winnow.run send-batch logs/batch_<timestamp>.json --confirm

# Tests
python -m pytest -v
```