import { describe, expect, it } from "vitest";
import { applyFilter, evaluate, reachable } from "../lib/filter";
import type { Criteria } from "../lib/models";
import { makeCandidate } from "./helpers";

describe("filter", () => {
  it("all pass becomes possible", () => {
    const candidate = makeCandidate({
      contacts: { email: "ada@example.org" },
      signals: { tier: "yes" },
    });
    const criteria: Criteria[] = [
      { name: "has_tier", predicate: (c) => c.signals.tier === "yes", cost: 1 },
    ];
    const { possible, noiseDropped } = applyFilter([candidate], criteria, reachable);
    expect(possible).toEqual([candidate]);
    expect(noiseDropped).toBe(0);
  });

  it("unreachable dropped", () => {
    const candidate = makeCandidate({ contacts: {} });
    const criteria: Criteria[] = [{ name: "always", predicate: () => true, cost: 0 }];
    const { possible, noiseDropped } = applyFilter([candidate], criteria, reachable);
    expect(possible).toHaveLength(0);
    expect(noiseDropped).toBe(1);
  });

  it("orders predicates by cost", () => {
    const order: string[] = [];
    const mk = (name: string): Criteria => ({
      name,
      predicate: () => {
        order.push(name);
        return true;
      },
      cost: name === "cheap" ? 1 : 10,
    });
    const candidate = makeCandidate({ contacts: { email: "x@y.com" } });
    expect(evaluate(candidate, [mk("expensive"), mk("cheap")])).toBe(true);
    expect(order).toEqual(["cheap", "expensive"]);
  });

  it("reachability keys", () => {
    expect(reachable(makeCandidate({ contacts: { email: "a@b.co" } }))).toBe(true);
    expect(reachable(makeCandidate({ contacts: { email: "   " } }))).toBe(false);
  });
});