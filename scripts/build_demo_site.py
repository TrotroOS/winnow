#!/usr/bin/env python3
"""Build static site/ from mock demo pipeline (for Vercel deploy)."""

from __future__ import annotations

import html
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from demo import _module_table, execute_demo  # noqa: E402


def _esc(text: object) -> str:
    return html.escape(str(text))


def render_html(data: dict[str, object]) -> str:
    situation = data["situation"]
    template_name = _esc(data["template_name"])
    criteria = data["criteria"]
    possible = data["possible"]
    noise_dropped = data["noise_dropped"]
    dedupe_dropped = data["dedupe_dropped"]
    by_predicate = data["by_predicate"]
    intent_lines = data["intent_lines"]
    preview = _esc(data["preview"])
    invariants = data["invariants"]
    filter_now = data["filter_now"]

    criteria_names = ", ".join(_esc(c.name) for c in criteria)  # type: ignore[union-attr]

    possible_rows = []
    for c in possible:  # type: ignore[union-attr]
        contact = (
            c.contacts.get("email")
            or c.contacts.get("linkedin")
            or c.contacts.get("dm", "")
        )
        sig = ", ".join(f"{k}={v}" for k, v in sorted(c.signals.items()) if v)
        possible_rows.append(
            f"<tr><td>{_esc(c.name)}</td><td>{_esc(c.org)}</td>"
            f"<td>{_esc(c.role)}</td><td>{_esc(contact)}</td>"
            f"<td class='muted'>{_esc(sig)}</td></tr>"
        )
    possible_table = "\n".join(possible_rows)

    pred_items = "".join(
        f"<li><strong>{_esc(k)}</strong>: {v}</li>"
        for k, v in sorted(by_predicate.items())  # type: ignore[union-attr]
    )

    intent_block = ""
    if intent_lines:
        lis = "".join(f"<li class='muted'>{_esc(line)}</li>" for line in intent_lines)  # type: ignore[union-attr]
        intent_block = f"<h3>Fixture intent vs filter</h3><ul>{lis}</ul>"

    inv_rows = []
    for name, ok, detail in invariants:  # type: ignore[assignment]
        status = "PASS" if ok else "FAIL"
        cls = "pass" if ok else "fail"
        inv_rows.append(
            f"<tr class='{cls}'><td>{_esc(name)}</td><td>{status}</td>"
            f"<td class='muted'>{_esc(detail) if detail and not ok else ''}</td></tr>"
        )
    invariant_table = "\n".join(inv_rows)

    module_lines = _module_table().strip().splitlines()
    mod_rows = []
    for line in module_lines[3:]:
        if " | " not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 4:
            mod_rows.append(
                "<tr>"
                + "".join(f"<td>{_esc(p)}</td>" for p in parts[:4])
                + "</tr>"
            )
    module_table = "\n".join(mod_rows)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Winnow — mock demo (first_revenue)</title>
  <style>
    :root {{
      color-scheme: light dark;
      --fg: #1a1a1a;
      --muted: #555;
      --bg: #fafafa;
      --border: rgba(127,127,127,.35);
      --pass: #0d7d3d;
      --fail: #b3261e;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --fg: #e8e8e8;
        --muted: #aaa;
        --bg: #121212;
        --pass: #6dd58c;
        --fail: #f2b8b5;
      }}
    }}
    body {{
      font-family: system-ui, sans-serif;
      line-height: 1.5;
      max-width: 52rem;
      margin: 2rem auto;
      padding: 0 1.25rem 3rem;
      color: var(--fg);
      background: var(--bg);
    }}
    h1 {{ font-size: 1.6rem; margin-bottom: 0.25rem; }}
    h2 {{ font-size: 1.15rem; margin-top: 2rem; border-bottom: 1px solid var(--border); padding-bottom: 0.25rem; }}
    h3 {{ font-size: 1rem; margin-top: 1.25rem; }}
    .muted {{ color: var(--muted); font-size: 0.92rem; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; margin: 0.5rem 0; }}
    th, td {{ border: 1px solid var(--border); padding: 0.35rem 0.5rem; text-align: left; vertical-align: top; }}
    th {{ background: rgba(127,127,127,0.12); }}
    tr.pass td:nth-child(2) {{ color: var(--pass); font-weight: 600; }}
    tr.fail td:nth-child(2) {{ color: var(--fail); font-weight: 600; }}
    .preview {{
      white-space: pre-wrap;
      font-size: 0.9rem;
      padding: 0.75rem;
      border-radius: 0.35rem;
      border: 1px solid var(--border);
      background: rgba(127,127,127,0.08);
    }}
    .badge {{ display: inline-block; padding: 0.15rem 0.45rem; border-radius: 0.25rem; background: rgba(127,127,127,0.2); font-size: 0.85rem; }}
  </style>
</head>
<body>
  <h1>Winnow mock demo</h1>
  <p class="muted">Binary-only: each row is <strong>POSSIBLE</strong> or dropped as <strong>NOISE</strong>. No scores or ranks. Built at deploy time from <code>fixtures/demo/</code> via real filter + outreach code.</p>

  <h2>Situation</h2>
  <p><span class="badge">{template_name}</span> · {_esc(situation.segment)}</p>
  <p class="muted">{_esc(situation.product)}<br>{_esc(situation.goal)}</p>
  <p><strong>Criteria:</strong> {criteria_names}</p>
  <p class="muted">Filter time (fixture clock): {_esc(filter_now.isoformat())}</p>

  <h2>POSSIBLE ({len(possible)})</h2>
  <table>
    <thead><tr><th>Name</th><th>Org</th><th>Role</th><th>Contact</th><th>Signals</th></tr></thead>
    <tbody>
    {possible_table}
    </tbody>
  </table>

  <h2>NOISE</h2>
  <p>Dropped after filter: <strong>{noise_dropped}</strong> · Dedupe before filter: <strong>{dedupe_dropped}</strong></p>
  <ul>{pred_items}</ul>
  {intent_block}

  <h2>Message preview (first POSSIBLE)</h2>
  <div class="preview">{preview}</div>
  <p class="muted">Batch staged: manual approve only · FAKE transport · spend $0.00</p>

  <h2>Invariant checks</h2>
  <table>
    <thead><tr><th>Check</th><th>Result</th><th>Detail</th></tr></thead>
    <tbody>{invariant_table}</tbody>
  </table>

  <h2>Module status</h2>
  <table>
    <thead><tr><th>Module</th><th>Implemented</th><th>Tested</th><th>Notes</th></tr></thead>
    <tbody>{module_table}</tbody>
  </table>

  <p class="muted" style="margin-top:2rem;">Live runs use <code>python3 scripts/demo.py</code> or <code>python -m winnow.run --dry-run</code> on your machine — not on Vercel.</p>
</body>
</html>
"""


def main() -> int:
    site_dir = _REPO_ROOT / "site"
    site_dir.mkdir(parents=True, exist_ok=True)
    data = execute_demo()
    if data["fail_lines"]:
        print("Warning: demo invariants failed:", data["fail_lines"], file=sys.stderr)
    html_doc = render_html(data)
    out = site_dir / "index.html"
    out.write_text(html_doc, encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())