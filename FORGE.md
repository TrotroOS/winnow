# Winnow on Forge + Rovo (Codegeist — Best Agents)

The `forge/` directory is a **thin Atlassian shell**. All binary-filter pipeline logic stays in the **`winnow/` Python package** at the repository root. Forge actions call the Python service over HTTP when configured; otherwise they return an aligned **stub** so you can develop manifests and prompts before `forge install`.

## Prerequisites

- Node.js 18+ (Forge uses `nodejs24.x` runtime)
- [@forge/cli](https://developer.atlassian.com/platform/forge/getting-started/) 10.8+ (`npm install -g @forge/cli@latest`)
- Rovo enabled on your Atlassian site (required for `rovo:agent`)
- Python 3.11+ (for the HTTP bridge, not inside Forge)

## Quick start

```bash
cd forge
npm install
forge login
forge register   # first time — copies app id into manifest via APP_ID
```

Create the app id once and export it for manifest parsing:

```bash
export APP_ID="<your-forge-app-id>"
```

Install on a development site (requires login):

```bash
forge deploy
forge install --site <your-site>.atlassian.net --product jira
```

Until install succeeds, use **stub actions** locally by deploying without `WINNOW_API_BASE_URL` — the Rovo agent still responds with POSSIBLE counts from the stub contract.

## Environment variables

| Variable | Where | Purpose |
|----------|--------|---------|
| `APP_ID` | Shell when running `forge deploy` | Substituted into `manifest.yml` `app.id` |
| `WINNOW_API_BASE_URL` | `forge variables set` (runtime) | Base URL of the Python HTTP bridge (no trailing slash) |
| `WINNOW_API_BASE_URL` | Shell export (optional) | Overrides default in `manifest.yml` `remotes.winnow-api.baseUrl` at deploy time |

Runtime (Forge):

```bash
forge variables set WINNOW_API_BASE_URL https://your-tunnel.example.com
forge deploy
```

Also allow the same host in `remotes` by exporting before deploy:

```bash
export WINNOW_API_BASE_URL=https://your-tunnel.example.com
forge deploy
```

## Python HTTP bridge (documented contract)

Start from the repo root:

```bash
pip install -e ".[dev]"
python -m winnow.http_server --host 0.0.0.0 --port 8791
```

Expose with a tunnel (ngrok, cloudflared, etc.) and point `WINNOW_API_BASE_URL` at that origin.

| Method | Path | Body | Response |
|--------|------|------|----------|
| `GET` | `/health` | — | `{"status":"ok","binary_only":true}` |
| `POST` | `/v1/describe` | `{"situation":"<text>"}` | `situation_type`, `criteria_names`, `binary_only` |
| `POST` | `/v1/run` | `{"situation":"<text>"}` | `possible_count`, `noise_dropped`, `outreach`, `audit_summary` |

Responses never include scores, rankings, or confidence — **BINARY ONLY** per `docs/winnow-spec.md` in the Project store.

## Rovo agent

After install:

1. Open Rovo chat in Jira.
2. Browse agents → enable **Winnow**.
3. Use conversation starters or ask to describe a situation / trigger a run.

Actions:

- **describe-situation** — parses situation + lists criteria names.
- **trigger-winnow-run** — runs pipeline (live API or stub) and returns audit summary.

## Jira global page (Forge UI)

Apps → Winnow (global page) shows whether the Python API is configured. This page is presentation only; it does not run Python.

## Logs

```bash
cd forge && forge logs
```

## Reference

- [Rovo agent module](https://developer.atlassian.com/platform/forge/manifest-reference/modules/rovo-agent/)
- [Action module](https://developer.atlassian.com/platform/forge/manifest-reference/modules/rovo-action/)
- [Invoke Remote](https://developer.atlassian.com/platform/forge/runtime-reference/invoke-remote-api/)