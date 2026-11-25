import type { Candidate, Criteria } from "./models";

export const REACHABILITY_KEYS = ["email", "linkedin", "dm"] as const;

function orderCriteria(criteria: readonly Criteria[]): Criteria[] {
  return [...criteria].sort((a, b) => a.cost - b.cost);
}

export function evaluate(
  candidate: Candidate,
  criteria: readonly Criteria[],
  options?: { now?: Date },
): boolean {
  for (const criterion of orderCriteria(criteria)) {
    if (!criterion.predicate(candidate, options)) {
      return false;
    }
  }
  return true;
}

export function reachable(candidate: Candidate): boolean {
  for (const key of REACHABILITY_KEYS) {
    const value = candidate.contacts[key];
    if (typeof value === "string" && value.trim()) {
      return true;
    }
  }
  return false;
}

export function applyFilter(
  candidates: readonly Candidate[],
  criteria: readonly Criteria[],
  reachability: (c: Candidate) => boolean,
  options?: { now?: Date },
): { possible: Candidate[]; noiseDropped: number } {
  const possible: Candidate[] = [];
  let noiseDropped = 0;
  for (const candidate of candidates) {
    if (!reachability(candidate)) {
      noiseDropped += 1;
      continue;
    }
    if (!evaluate(candidate, criteria, options)) {
      noiseDropped += 1;
      continue;
    }
    possible.push(candidate);
  }
  return { possible, noiseDropped };
}