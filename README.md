# Winnow

An agent that finds the users a startup needs to serve and bulk-outreaches them.

**Core rule — BINARY ONLY:** every candidate is either POSSIBLE or NOISE. Predicates return `bool` only; reachability is a separate hard gate; dropped noise is counted, not stored. No scores, ranking, confidence, weights, or top-N.

## Architecture: Python core vs Forge shell

| Layer | Location | Role |
|-------|-----------|------|
| **Python core** | `winnow/` | Situation parse → binary filter → outreach; audit logs; HTTP bridge for remotes |
| **Forge + Rovo** | `forge/` | Atlassian entry (Rovo agent, actions, Jira global page). Calls Python via HTTP or uses stubs |

Python does **not** run inside Forge. Configure `WINNOW_API_BASE_URL` on the Forge app and run `python -m winnow.http_server` (see [FORGE.md](./FORGE.md)).

## Requirements

- Python 3.11+
- Node.js 18+ and Forge CLI 10.8+ (only for `forge/`)

## Install (Python)

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

## HTTP bridge (Forge / integrations)

```bash
python -m winnow.http_server --port 8791
```

`POST /v1/run` and `POST /v1/describe` — documented in [FORGE.md](./FORGE.md).

## Running tests

Tests use fixture candidates and in-memory source adapters only — no network.

```bash
pytest
```

## Package layout

- `winnow/` — pipeline modules (`situation_parser`, `criteria_builder`, `source_router`, `normalize`, `dedupe`, `binary_filter`, `outreach_engine`, `orchestrator`, `audit`, `http_bridge`, `http_server`)
- `winnow/adapters/` — swappable source adapters (`FixtureSourceAdapter` for tests)
- `forge/` — Forge manifest, Rovo agent prompt, actions, static Jira page

Full product spec: Project store `docs/winnow-spec.md`. Forge setup: [FORGE.md](./FORGE.md).