import { describe, expect, it } from "vitest";
import { buildCriteria, parseSituation } from "../lib/criteria/builder";

describe("criteria builder", () => {
  it("resolves first_revenue", () => {
    const situation = parseSituation({
      goal: "first_revenue: land customers",
      segment: "independent coffee shops",
      situation_type: "first_revenue",
    });
    const { templateName, criteria } = buildCriteria(situation);
    expect(templateName).toBe("first_revenue");
    expect(criteria.map((c) => c.name)).toEqual([
      "revenue_ready",
      "recent_activity",
      "decision_maker",
    ]);
  });
});