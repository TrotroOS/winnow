import type { Candidate, Criteria } from "../models";

const BODIES: Record<string, string> = {
  first_revenue:
    "Hi {name},\n\nAt {org}, {matched_signal} caught my eye. Would you be open to seeing how we might help you ship faster?",
};

function matchedSignal(candidate: Candidate, criteria: readonly Criteria[]): string {
  for (const c of criteria) {
    if (c.predicate(candidate)) {
      const seg = candidate.signals.segment;
      if (seg) return `segment=${seg}`;
      return c.name;
    }
  }
  return candidate.role || "your work";
}

export function buildMessage(
  situationType: string,
  candidate: Candidate,
  criteria: readonly Criteria[],
): string {
  const template = BODIES[situationType.trim().toLowerCase()] ?? BODIES.first_revenue!;
  const ms = matchedSignal(candidate, criteria);
  return template
    .replace("{name}", candidate.name)
    .replace("{org}", candidate.org)
    .replace("{matched_signal}", ms);
}