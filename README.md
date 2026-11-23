# Winnow

An agent that finds the users a startup needs to serve and bulk-outreaches them.

**Core rule — BINARY ONLY:** every candidate is either POSSIBLE or NOISE. Predicates return `bool` only; reachability is a separate hard gate; dropped noise is counted, not stored. No scores, ranking, confidence, weights, or top-N.

## Requirements

- Python 3.11+

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Configuration (environment)

| Variable | Description |
|----------|-------------|
| `WINNOW_SPEND_CAP_CENTS` | Per-run enrichment spend cap (0 = unlimited) |
| `WINNOW_ENRICHMENT_API_KEY` | API key for paid enrichment (never hardcoded) |
| `WINNOW_CSV_SOURCE_DIR` | Directory of local `*.csv` candidate files (cost rank 1) |
| `WINNOW_GITHUB_TOKEN` | GitHub API token for user search (cost rank 2; omitted in tests) |

## Running tests

Tests use fixture candidates and in-memory source adapters only — no network.

```bash
python3 -m pytest
```

## Dry-run CLI

```bash
python3 -m winnow run --situation "B2B SaaS launch need CTO in Ghana" --json
```

Source cost order (cheapest first): fixture (0) → CSV directory (1) → GitHub search (2, only when `WINNOW_GITHUB_TOKEN` is set).

## Package layout

- `winnow/` — pipeline modules (`situation_parser`, `criteria_builder`, `source_router`, `normalize`, `dedupe`, `binary_filter`, `outreach_engine`, `orchestrator`, `audit`)
- `winnow/adapters/` — swappable source adapters (`FixtureSourceAdapter` for tests)

Full product spec: Project store `docs/winnow-spec.md`.