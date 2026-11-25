import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { Candidate } from "../models";
import { normalize } from "../normalize";
import type { SourceAdapter } from "./adapter";

export class FixtureSource implements SourceAdapter {
  readonly name = "fixtures";
  readonly costPerCall = 0;

  constructor(private readonly root: string) {}

  search(_queries: readonly string[], limit: number): Candidate[] {
    const possible = JSON.parse(
      readFileSync(join(this.root, "possible.json"), "utf8"),
    ) as Record<string, unknown>[];
    const noise = JSON.parse(
      readFileSync(join(this.root, "noise.json"), "utf8"),
    ) as Record<string, unknown>[];
    const rows = [...possible, ...noise].map((r) => normalize(r, "demo_fixture"));
  return limit <= 0 ? [] : rows.slice(0, limit);
  }
}