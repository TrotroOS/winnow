#!/usr/bin/env node
/**
 * Vercel build: regenerate site/index.html via Python demo when available,
 * otherwise keep committed site/index.html (static fallback).
 */
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const indexHtml = join(root, "site", "index.html");

const py = spawnSync("python3", ["scripts/build_demo_site.py"], {
  cwd: root,
  stdio: "inherit",
});

if (py.status === 0) {
  console.log("build: regenerated site/index.html from mock demo");
  process.exit(0);
}

console.warn(
  "build: python3 build_demo_site.py failed or missing; using committed site/index.html",
);
if (!existsSync(indexHtml)) {
  console.error("build: site/index.html missing — run python3 scripts/build_demo_site.py locally");
  process.exit(1);
}
process.exit(0);