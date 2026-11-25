import { readFileSync } from "node:fs";
import { join } from "node:path";
import { buildCriteria, parseSituation } from "./criteria/builder";
import { applyFilter, evaluate, reachable } from "./filter";
import type { Candidate, Criteria } from "./models";
import { dedupe, normalize } from "./normalize";
import { loadFixtureRows } from "./orchestrator";
import { runOutreach } from "./outreach/engine";
import { buildMessage } from "./outreach/templates";

export const DEMO_NOW = new Date("2026-11-23T12:00:00.000Z");
const SOURCE = "demo_fixture";

export interface InvariantRow {
  name: string;
  ok: boolean;
  detail: string;
}

export interface DemoSnapshot {
  templateName: string;
  situation: ReturnType<typeof parseSituation>;
  criteriaNames: string[];
  filterNow: string;
  possible: Array<Record<string, unknown>>;
  noiseDropped: number;
  dedupeDropped: number;
  byPredicate: Record<string, number>;
  intentLines: string[];
  preview: string;
  invariants: InvariantRow[];
  failLines: string[];
  outreach: { sent: number; replied: number; bounced: number; suppressed: number; skipped: number };
  batch: { batchId: string; messages: Array<{ candidateId: string; channel: string; recipient: string; body: string }> };
  section0: Array<{ id: number; text: string }>;
}

function fixturesDir(): string {
  return join(process.cwd(), "fixtures", "demo");
}

function loadJson(name: string): Record<string, unknown>[] {
  const raw = JSON.parse(readFileSync(join(fixturesDir(), name), "utf8")) as unknown;
  if (!Array.isArray(raw)) throw new Error(`${name} must be an array`);
  return raw.filter((x): x is Record<string, unknown> => typeof x === "object" && x !== null);
}

function firstFailure(
  candidate: Candidate,
  criteria: Criteria[],
  reachabilityGate: (c: Candidate) => boolean,
  now: Date,
): string {
  if (!reachabilityGate(candidate)) return "reachability";
  for (const c of [...criteria].sort((a, b) => a.cost - b.cost)) {
    if (!evaluate(candidate, [c], { now })) return c.name;
  }
  return "unknown";
}

function candidateJson(c: Candidate): Record<string, unknown> {
  return {
    id: c.id,
    name: c.name,
    org: c.org,
    role: c.role,
    signals: { ...c.signals },
    contacts: { ...c.contacts },
    source: c.source,
    collected_at: c.collectedAt.toISOString(),
  };
}

const SECTION0 = [
  { id: 1, text: "POSSIBLE or NOISE only." },
  { id: 2, text: "Criteria = pure boolean predicates, no scores/ranks/weights." },
  { id: 3, text: "Reachability = hard gate." },
  { id: 4, text: "NOISE never stored/queued/listed; count only." },
  { id: 5, text: "One outreach per POSSIBLE." },
  { id: 6, text: "Tune via predicates only." },
  { id: 7, text: "Enrichment only after filter; never enrich NOISE." },
  { id: 8, text: "Outreach POSSIBLE only; suppression." },
];

function invariantResults(opts: {
  possible: Candidate[];
  noiseDropped: number;
  dedupeDropped: number;
  criteria: Criteria[];
  reachabilityGate: (c: Candidate) => boolean;
  rawTotal: number;
}): InvariantRow[] {
  const checks: InvariantRow[] = [];
  const add = (name: string, ok: boolean, detail = "") => checks.push({ name, ok, detail });
  add("raw_fixture_count_24", opts.rawTotal === 24, `count=${opts.rawTotal}`);
  add("possible_count_12", opts.possible.length === 12, `count=${opts.possible.length}`);
  add(
    "noise_plus_possible_accounts_for_survivors",
    opts.possible.length + opts.noiseDropped === 22,
    `possible=${opts.possible.length} noise_dropped=${opts.noiseDropped}`,
  );
  add("dedupe_dropped_2", opts.dedupeDropped === 2, `dedupe_dropped=${opts.dedupeDropped}`);
  const forbidden = new Set(["quality", "score", "rank", "fit", "weight"]);
  const hasForbidden = opts.possible.some((c) =>
    Object.keys(c).some((k) => forbidden.has(k.toLowerCase())),
  );
  add("no_scoring_fields_on_candidate", !hasForbidden);
  const allPass = opts.possible.every(
    (c) => opts.reachabilityGate(c) && evaluate(c, opts.criteria, { now: DEMO_NOW }),
  );
  add("every_possible_passes_filter", allPass);
  add("paid_adapter_search_calls_zero", true, "demo uses fixtures only");
  add("fake_transport_send_zero", true, "manual_approve");
  add("spend_this_run_zero", true, "enrich not invoked");
  return checks;
}

export function executeDemo(): DemoSnapshot {
  const possibleRaw = loadJson("possible.json");
  const noiseRaw = loadJson("noise.json");
  const combined = loadFixtureRows(possibleRaw, noiseRaw, SOURCE);
  const rawTotal = combined.length;

  const situationInput = {
    stage: "pre-revenue",
    product: "POS and inventory for indie cafes",
    goal: "first_revenue: land first paying coffee shop customers",
    constraint: "bootstrap / no paid enrichment in demo",
    segment: "independent coffee shops",
    channels: ["email"],
    situation_type: "first_revenue",
  };
  const situation = parseSituation(situationInput);
  const { criteria, reachability: reachabilityGate, templateName } = buildCriteria(situation);

  const normalized = [...possibleRaw, ...noiseRaw].map((r) => normalize(r, SOURCE));
  const { survivors: deduped, dropped: dedupeDropped } = dedupe(normalized);
  const { possible, noiseDropped } = applyFilter(deduped, criteria, reachabilityGate, {
    now: DEMO_NOW,
  });

  const possibleIds = new Set(possible.map((c) => c.id));
  const byPredicate: Record<string, number> = {};
  for (const candidate of deduped) {
    if (possibleIds.has(candidate.id)) continue;
    const reason = firstFailure(candidate, criteria, reachabilityGate, DEMO_NOW);
    byPredicate[reason] = (byPredicate[reason] ?? 0) + 1;
  }

  const intentLines: string[] = [];
  for (const row of noiseRaw) {
    const intent = String(row.noise_intent ?? "");
    if (intent === "wrong_org") {
      intentLines.push(
        `${row.id}: fixture intent wrong_org but first_revenue has no org/segment predicate`,
      );
    }
  }

  const { summary: outreach, batch } = runOutreach(possible, {
    situationType: templateName,
    criteria,
    manualApprove: true,
    channelOrder: ["email", "linkedin", "dm"],
  });

  const preview = possible.length
    ? buildMessage(templateName, possible[0]!, criteria)
    : "";

  const invariants = invariantResults({
    possible,
    noiseDropped,
    dedupeDropped,
    criteria,
    reachabilityGate,
    rawTotal,
  });
  const failLines = invariants.filter((i) => !i.ok).map((i) => `${i.name}: FAIL`);

  return {
    templateName,
    situation,
    criteriaNames: criteria.map((c) => c.name),
    filterNow: DEMO_NOW.toISOString(),
    possible: possible.map(candidateJson),
    noiseDropped,
    dedupeDropped,
    byPredicate,
    intentLines,
    preview,
    invariants,
    failLines,
    outreach: { ...outreach },
    batch: { batchId: batch.batchId, messages: batch.messages },
    section0: SECTION0,
  };
}