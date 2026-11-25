import type { Candidate } from "../models";

function signal(candidate: Candidate, key: string): string {
  const value = candidate.signals[key] ?? "";
  return typeof value === "string" ? value.trim() : "";
}

function isYes(candidate: Candidate, key: string): boolean {
  return ["yes", "true", "1"].includes(signal(candidate, key).toLowerCase());
}

export function hasSignalWithin(
  days: number,
  signalKey = "activity_days",
): (candidate: Candidate) => boolean {
  return (candidate) => {
    const raw = signal(candidate, signalKey);
    if (!raw) return false;
    const elapsed = Number.parseInt(raw, 10);
    if (Number.isNaN(elapsed)) return false;
    return elapsed <= days;
  };
}

export function roleMatches(roles: readonly string[]): (candidate: Candidate) => boolean {
  const normalized = roles.map((r) => r.toLowerCase());
  return (candidate) => {
    const role = candidate.role.toLowerCase();
    return normalized.some((r) => role.includes(r) || r.includes(role));
  };
}

export function orgInSegment(segment: string): (candidate: Candidate) => boolean {
  const needle = segment.toLowerCase();
  return (candidate) =>
    candidate.org.toLowerCase().includes(needle) ||
    signal(candidate, "segment").toLowerCase().includes(needle);
}

export function signalIsYes(key: string): (candidate: Candidate) => boolean {
  return (candidate) => isYes(candidate, key);
}