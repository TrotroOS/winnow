# Winnow

An agent that finds the users a startup needs to serve, for whatever situation
the startup is in, and bulk-outreaches them.

## Core rule — BINARY ONLY

A candidate is either POSSIBLE or NOISE. There is no third state.

- Every criterion is a pure predicate returning bool. No floats, no weights,
  no confidence, no "fit score", no ranking, no top-N, no priority column.
- Reachability is a HARD GATE, not a criterion.
- NOISE is deleted. It is never stored, queued, or returned in an output list.
  Only a count of dropped candidates is logged.
- Every POSSIBLE candidate receives exactly one outreach action. No triage.
- Tuning happens by adding/removing/tightening a predicate. Never by adding
  a score.

If you find yourself writing a number that represents "how good" a candidate
is, stop — that is a bug. Report it instead.

## Pipeline

```
situation parser -> criteria builder -> source router -> search+extract ->
normalize -> dedupe -> binary filter (+reachability gate) -> POSSIBLE[] ->
outreach engine (batched, throttled, suppressed) -> tracker -> feedback
```

## Data model

**Candidate:**
  id, name, org, role, signals: dict, contacts: dict,
  source, collected_at

**Criteria:** list of {name, predicate(candidate) -> bool}

**Reachability:** predicate(candidate) -> bool

**RunResult:**
  situation_type, criteria_names, sources, possible: list[Candidate],
  noise_dropped: int, outreach: {sent, replied, bounced, suppressed, skipped}

## Non-negotiables

1. Enrichment (paid API calls) happens ONLY after a candidate passes the
   binary filter. Never enrich NOISE.
2. Source router tries cheapest sources first.
3. Outreach only ever targets POSSIBLE. Suppression list prevents re-contact.
4. Per-run spend cap is enforced in the orchestrator; when exhausted, stop
   enriching and log the backlog count.
5. Every run writes an audit log: situation -> criteria -> sources ->
   possible count -> outreach counts.
6. Pure functions for the filter and predicates. No I/O inside them.
7. No network calls in unit tests. Use fixture candidates.

## Conventions

- **Next.js 14** App Router under `app/`; **TypeScript** with `strict` enabled.
- **Vitest** in `tests/` mirrors Python `tests/` for core pipeline (`filter`, `normalize`, `criteria`, `orchestrator`).
- Core pipeline lives only under `lib/`: `models`, `filter`, `normalize`, `criteria/`, `sources/`, `outreach/`, `orchestrator`, `store` — no React or `next/*` imports in `lib/`.
- Demo fixtures: `fixtures/demo/possible.json` and `fixtures/demo/noise.json` (12+12 rows; each noise row has `_reason`).
- Source adapters implement `lib/sources/adapter.ts` so sources stay swappable.
- Secrets from environment variables; never hardcode API keys.