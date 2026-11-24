/** @param {string} text */
export function esc(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** @param {import("./types.mjs").DemoSnapshot} data */
export function renderPage(data) {
  const templateName = esc(data.template_name);
  const situation = data.situation;
  const criteriaNames = data.criteria_names.map(esc).join(", ");

  const possibleRows = data.possible
    .map((c) => {
      const contact =
        c.contacts.email ||
        c.contacts.linkedin ||
        c.contacts.dm ||
        "";
      const sig = Object.entries(c.signals)
        .filter(([, v]) => v)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([k, v]) => `${k}=${v}`)
        .join(", ");
      return `<tr><td>${esc(c.name)}</td><td>${esc(c.org)}</td><td>${esc(c.role)}</td><td>${esc(contact)}</td><td class='muted'>${esc(sig)}</td></tr>`;
    })
    .join("\n");

  const predItems = Object.entries(data.by_predicate)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(
      ([k, v]) => `<li><strong>${esc(k)}</strong>: ${v}</li>`,
    )
    .join("");

  let intentBlock = "";
  if (data.intent_lines.length) {
    const lis = data.intent_lines
      .map((line) => `<li class='muted'>${esc(line)}</li>`)
      .join("");
    intentBlock = `<h3>Fixture intent vs filter</h3><ul>${lis}</ul>`;
  }

  const invariantRows = data.invariants
    .map(({ name, ok, detail }) => {
      const status = ok ? "PASS" : "FAIL";
      const cls = ok ? "pass" : "fail";
      const detailCell =
        detail && !ok ? esc(detail) : "";
      return `<tr class='${cls}'><td>${esc(name)}</td><td>${status}</td><td class='muted'>${detailCell}</td></tr>`;
    })
    .join("\n");

  const moduleRows = data.modules
    .map(
      (row) =>
        `<tr><td>${esc(row.module)}</td><td>${esc(row.implemented)}</td><td>${esc(row.tested)}</td><td>${esc(row.notes)}</td></tr>`,
    )
    .join("\n");

  const preview = esc(data.preview);

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Winnow — mock demo (first_revenue)</title>
  <style>
    :root {
      color-scheme: light dark;
      --fg: #1a1a1a;
      --muted: #555;
      --bg: #fafafa;
      --border: rgba(127,127,127,.35);
      --pass: #0d7d3d;
      --fail: #b3261e;
    }
    @media (prefers-color-scheme: dark) {
      :root {
        --fg: #e8e8e8;
        --muted: #aaa;
        --bg: #121212;
        --pass: #6dd58c;
        --fail: #f2b8b5;
      }
    }
    body {
      font-family: system-ui, sans-serif;
      line-height: 1.5;
      max-width: 52rem;
      margin: 2rem auto;
      padding: 0 1.25rem 3rem;
      color: var(--fg);
      background: var(--bg);
    }
    h1 { font-size: 1.6rem; margin-bottom: 0.25rem; }
    h2 { font-size: 1.15rem; margin-top: 2rem; border-bottom: 1px solid var(--border); padding-bottom: 0.25rem; }
    h3 { font-size: 1rem; margin-top: 1.25rem; }
    .muted { color: var(--muted); font-size: 0.92rem; }
    table { width: 100%; border-collapse: collapse; font-size: 0.88rem; margin: 0.5rem 0; }
    th, td { border: 1px solid var(--border); padding: 0.35rem 0.5rem; text-align: left; vertical-align: top; }
    th { background: rgba(127,127,127,0.12); }
    tr.pass td:nth-child(2) { color: var(--pass); font-weight: 600; }
    tr.fail td:nth-child(2) { color: var(--fail); font-weight: 600; }
    .preview {
      white-space: pre-wrap;
      font-size: 0.9rem;
      padding: 0.75rem;
      border-radius: 0.35rem;
      border: 1px solid var(--border);
      background: rgba(127,127,127,0.08);
    }
    .badge { display: inline-block; padding: 0.15rem 0.45rem; border-radius: 0.25rem; background: rgba(127,127,127,0.2); font-size: 0.85rem; }
  </style>
</head>
<body>
  <h1>Winnow mock demo</h1>
  <p class="muted">Binary-only: each row is <strong>POSSIBLE</strong> or dropped as <strong>NOISE</strong>. No scores or ranks. Served from <code>fixtures/demo/</code> snapshot (real filter + outreach pipeline at build time).</p>

  <h2>Situation</h2>
  <p><span class="badge">${templateName}</span> · ${esc(situation.segment)}</p>
  <p class="muted">${esc(situation.product)}<br>${esc(situation.goal)}</p>
  <p><strong>Criteria:</strong> ${criteriaNames}</p>
  <p class="muted">Filter time (fixture clock): ${esc(data.filter_now)}</p>

  <h2>POSSIBLE (${data.possible.length})</h2>
  <table>
    <thead><tr><th>Name</th><th>Org</th><th>Role</th><th>Contact</th><th>Signals</th></tr></thead>
    <tbody>
    ${possibleRows}
    </tbody>
  </table>

  <h2>NOISE</h2>
  <p>Dropped after filter: <strong>${data.noise_dropped}</strong> · Dedupe before filter: <strong>${data.dedupe_dropped}</strong></p>
  <ul>${predItems}</ul>
  ${intentBlock}

  <h2>Message preview (first POSSIBLE)</h2>
  <div class="preview">${preview}</div>
  <p class="muted">Batch staged: manual approve only · FAKE transport · spend $0.00</p>

  <h2>Invariant checks</h2>
  <table>
    <thead><tr><th>Check</th><th>Result</th><th>Detail</th></tr></thead>
    <tbody>${invariantRows}</tbody>
  </table>

  <h2>Module status</h2>
  <table>
    <thead><tr><th>Module</th><th>Implemented</th><th>Tested</th><th>Notes</th></tr></thead>
    <tbody>${moduleRows}</tbody>
  </table>

  <p class="muted" style="margin-top:2rem;">Live runs use <code>python3 scripts/demo.py</code> or <code>python -m winnow.run --dry-run</code> on your machine — not on Vercel.</p>
</body>
</html>`;
}