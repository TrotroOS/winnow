import type { Candidate } from "../lib/models";

export function makeCandidate(overrides: Partial<Candidate> = {}): Candidate {
  return {
    id: "cand-1",
    name: "Ada Lovelace",
    org: "Example Org",
    role: "Engineer",
    signals: {},
    contacts: {},
    source: "fixture",
    collectedAt: new Date("2026-01-01T00:00:00.000Z"),
    ...overrides,
  };
}