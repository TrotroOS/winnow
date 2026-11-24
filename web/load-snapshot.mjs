import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const webDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(webDir, "..");

/** @returns {import("./types.mjs").DemoSnapshot} */
export function loadSnapshot() {
  const path = join(repoRoot, "public", "demo-snapshot.json");
  const raw = readFileSync(path, "utf8");
  return JSON.parse(raw);
}