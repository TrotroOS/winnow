#!/usr/bin/env node
/**
 * Vercel build: refresh public/demo-snapshot.json via Python when available,
 * otherwise keep the committed snapshot. Optionally regenerate site/index.html.
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
  console.log("build: wrote public/demo-snapshot.json from mock demo");
} else {
  console.warn(
    "build: export_demo_snapshot.py failed or python3 missing; using committed snapshot",
  );
  if (!existsSync(snapshot)) {
    console.error(
      "build: public/demo-snapshot.json missing — run python3 scripts/export_demo_snapshot.py locally",
    );
    process.exit(1);
  }
}

const pySite = spawnSync("python3", ["scripts/build_demo_site.py"], {
  cwd: root,
  stdio: "inherit",
  env: {
    ...process.env,
    PYTHONPATH: join(root, "src"),
  },
});

if (pySite.status === 0) {
  console.log("build: regenerated site/index.html (legacy static mirror)");
} else {
  console.warn("build: site/index.html not refreshed (optional)");
}

console.log("build: Node web app ready (api/index.mjs)");
process.exit(0);