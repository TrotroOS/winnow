import { describe, expect, it } from "vitest";
import { executeDemo } from "../lib/demo-run";

describe("demo run", () => {
  it("fixture pipeline invariants", () => {
    const snap = executeDemo();
    expect(snap.possible).toHaveLength(12);
    expect(snap.noiseDropped).toBe(10);
    expect(snap.dedupeDropped).toBe(2);
    expect(snap.failLines).toHaveLength(0);
  });
});