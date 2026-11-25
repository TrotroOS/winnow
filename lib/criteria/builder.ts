import type { Candidate, Criteria, StartupSituation } from "../models";
import { buildFromTemplate } from "./templates";

const GOAL_KEYWORDS: Record<string, readonly string[]> = {
  first_revenue: ["first revenue", "first customer", "paying customer", "revenue"],
};

export function parseSituation(data: Record<string, unknown>): StartupSituation {
  const rawChannels = data.channels;
  let channels: string[];
  if (typeof rawChannels === "string") {
    channels = rawChannels ? [rawChannels] : [];
  } else if (Array.isArray(rawChannels)) {
    channels = rawChannels.map(String);
  } else {
    channels = [];
  }
  let goal = String(data.goal ?? "");
  const situationType = data.situation_type;
  if (situationType) {
    const prefix = String(situationType).trim().toLowerCase();
    if (!goal.toLowerCase().startsWith(`${prefix}:`)) {
      goal = `${prefix}: ${goal}`.replace(/^:\s*/, "");
    }
  }
  return {
    stage: String(data.stage ?? ""),
    product: String(data.product ?? ""),
    goal,
    constraint: String(data.constraint ?? ""),
    segment: String(data.segment ?? ""),
    channels,
  };
}

function resolveTemplateName(situation: StartupSituation): string {
  const head = situation.goal.split(":", 1)[0]?.trim().toLowerCase() ?? "";
  if (head in GOAL_KEYWORDS || head === "first_revenue") return head || "first_revenue";
  const haystack = [situation.goal, situation.stage, situation.product, situation.constraint]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  const matches: string[] = [];
  for (const [name, phrases] of Object.entries(GOAL_KEYWORDS)) {
    if (phrases.some((phrase) => haystack.includes(phrase))) matches.push(name);
  }
  if (matches.length === 1) return matches[0]!;
  if (matches.length > 1) {
    throw new Error(`Ambiguous situation; matched ${matches.join(", ")}`);
  }
  throw new Error("Unknown situation; set situation_type explicitly.");
}

export function buildCriteria(
  situation: StartupSituation,
): { criteria: Criteria[]; reachability: (c: Candidate) => boolean; templateName: string } {
  const templateName = resolveTemplateName(situation);
  const { criteria, reachability } = buildFromTemplate(templateName, situation);
  return { criteria, reachability, templateName };
}