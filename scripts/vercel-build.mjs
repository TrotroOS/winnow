#!/usr/bin/env node
/**
 * Optional: refresh public/demo-snapshot.json from the Python mock demo (legacy JSON mirror).
 * The Next.js inspection UI reads fixtures/demo/*.json directly via lib/demo-run.ts.
 */
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const snapshot = join(root, "public", "demo-snapshot.json");

const pyExport = spawnSync("python3", ["scripts/export_demo_snapshot.py"], {
  cwd: root,
  stdio: "inherit",
  env: {
    ...process.env,
    PYTHONPATH: join(root, "src"),
  },
});

if (pyExport.status === 0) {
  console.log("export: wrote public/demo-snapshot.json");
} else {
  console.warn("export: python export skipped or failed");
  if (!existsSync(snapshot)) {
    console.warn("export: no committed demo-snapshot.json (Next UI does not require it)");
  }
}