import { describe, expect, it } from "vitest";
import { dedupe, normalize } from "../lib/normalize";
import { makeCandidate } from "./helpers";

describe("normalize", () => {
  it("maps fields", () => {
    const collected = new Date("2026-03-01T15:30:00.000Z");
    const c = normalize(
      {
        id: "src-9",
        name: "Alex Kim",
        org: "Winnow Labs",
        role: "CEO",
        signals: { segment: "b2b" },
        contacts: { email: "alex@winnow.test" },
        collected_at: collected.toISOString(),
      },
      "mock",
    );
    expect(c.id).toBe("src-9");
    expect(c.collectedAt.toISOString()).toBe(collected.toISOString());
  });

  it("dedupe keeps newest", () => {
    const older = makeCandidate({
      id: "",
      name: "Sam",
      org: "Co",
      collectedAt: new Date("2026-01-01T00:00:00.000Z"),
    });
    const newer = makeCandidate({
      id: "",
      name: "Sam",
      org: "Co",
      collectedAt: new Date("2026-02-01T00:00:00.000Z"),
    });
    const { survivors, dropped } = dedupe([older, newer]);
    expect(survivors).toHaveLength(1);
    expect(survivors[0]!.collectedAt).toEqual(newer.collectedAt);
    expect(dropped).toBe(1);
  });
});