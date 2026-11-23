# Winnow (project guide)

An agent that finds the users a startup needs to serve and bulk-outreaches them.

## Binary only (non-negotiable)

A candidate is **POSSIBLE** or **NOISE** — no third state. Criteria are pure `bool` predicates. No scores, weights, confidence, fit, ranking, priority, or top-N. Reachability is a hard gate, not a scored criterion. NOISE is dropped (count only). Every POSSIBLE candidate gets exactly one outreach action.

If you add a numeric "how good" field, that is a bug.

See full spec in the Project store (`docs/winnow-spec.md`).

## Repository layout

```
pyproject.toml          # pytest, src layout
src/winnow/
  models.py             # Candidate, Criteria, RunResult, StartupSituation
  filter.py             # binary filter (stub)
  criteria/             # predicate builders (empty package)
  sources/adapter.py    # SourceAdapter protocol
  outreach/             # outreach engine (empty package)
  orchestrator.py       # pipeline coordinator (stub)
tests/
  conftest.py           # make_candidate() factory
```

Python 3.11+, type hints, dataclasses. No network in unit tests. Secrets from env vars.