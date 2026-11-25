import type { Candidate } from "./models";

const EPOCH_UTC = new Date("1970-01-01T00:00:00.000Z");

function stringField(raw: Record<string, unknown>, key: string): string {
  const value = raw[key];
  if (value == null) return "";
  return String(value);
}

function stringDict(value: unknown): Record<string, string> {
  if (typeof value !== "object" || value == null || Array.isArray(value)) {
    return {};
  }
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(value)) {
    if (typeof k === "string") {
      out[k] = v == null ? "" : String(v);
    }
  }
  return out;
}

function parseCollectedAt(value: unknown): Date {
  if (value == null) return EPOCH_UTC;
  if (value instanceof Date) return value;
  if (typeof value === "string") {
    if (!value.trim()) return EPOCH_UTC;
    return new Date(value);
  }
  return EPOCH_UTC;
}

export function normalize(raw: Record<string, unknown>, source: string): Candidate {
  return {
    id: stringField(raw, "id"),
    name: stringField(raw, "name"),
    org: stringField(raw, "org"),
    role: stringField(raw, "role"),
    signals: stringDict(raw.signals),
    contacts: stringDict(raw.contacts),
    source,
    collectedAt: parseCollectedAt(raw.collected_at),
  };
}

function dedupeKey(candidate: Candidate): string {
  const id = candidate.id.trim();
  if (id) return `id:${id.toLowerCase()}`;
  return `person:${candidate.name.toLowerCase().trim()}|${candidate.org.toLowerCase().trim()}`;
}

function newer(a: Candidate, b: Candidate): Candidate {
  return a.collectedAt > b.collectedAt ? a : b;
}

export function dedupe(
  candidates: readonly Candidate[],
): { survivors: Candidate[]; dropped: number } {
  if (!candidates.length) return { survivors: [], dropped: 0 };
  const firstIndex = new Map<string, number>();
  const best = new Map<string, Candidate>();
  candidates.forEach((candidate, index) => {
    const key = dedupeKey(candidate);
    if (!firstIndex.has(key)) {
      firstIndex.set(key, index);
      best.set(key, candidate);
      return;
    }
    const prev = best.get(key)!;
    best.set(key, newer(candidate, prev));
  });
  const ordered = [...best.keys()].sort(
    (a, b) => (firstIndex.get(a) ?? 0) - (firstIndex.get(b) ?? 0),
  );
  const survivors = ordered.map((k) => best.get(k)!);
  return { survivors, dropped: candidates.length - survivors.length };
}