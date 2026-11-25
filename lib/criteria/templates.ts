import { reachable } from "../filter";
import type { Candidate, Criteria, StartupSituation } from "../models";
import * as p from "./predicates";

type TemplateFn = (
  situation: StartupSituation,
) => { criteria: Criteria[]; reachability: (c: Candidate) => boolean };

function firstRevenue(situation: StartupSituation) {
  void situation;
  return {
    criteria: [
      { name: "revenue_ready", predicate: p.signalIsYes("revenue_ready"), cost: 1 },
      { name: "recent_activity", predicate: p.hasSignalWithin(60), cost: 2 },
      {
        name: "decision_maker",
        predicate: p.roleMatches(["founder", "ceo", "head", "director", "vp", "owner"]),
        cost: 3,
      },
    ],
    reachability: reachable,
  };
}

const TEMPLATES: Record<string, TemplateFn> = {
  first_revenue: firstRevenue,
};

export function buildFromTemplate(
  templateName: string,
  situation: StartupSituation,
): { criteria: Criteria[]; reachability: (c: Candidate) => boolean } {
  const key = templateName.trim().toLowerCase();
  const factory = TEMPLATES[key];
  if (!factory) {
    throw new Error(`Unknown template ${templateName}; known: ${Object.keys(TEMPLATES).join(", ")}`);
  }
  return factory(situation);
}