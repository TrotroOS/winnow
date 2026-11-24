import { buildCriteria, parseSituation } from "./criteria/builder";
import { applyFilter } from "./filter";
import type { Candidate, RunResult } from "./models";
import { dedupe, normalize } from "./normalize";
import { runOutreach } from "./outreach/engine";
import { route } from "./router";
import type { WinnowStore } from "./store";

export interface RunConfig {
  filterNow?: Date;
  manualApprove?: boolean;
  store?: WinnowStore;
  searchLimit?: number;
}

export function run(
  situationInput: Record<string, unknown>,
  config: RunConfig = {},
): RunResult {
  const situation = parseSituation(situationInput);
  const { criteria, reachability, templateName } = buildCriteria(situation);
  const adapters = route(situation, criteria);
  const sources = adapters.map((a) => a.name);
  const queries = [situation.segment, situation.product].filter(Boolean);
  const limit = config.searchLimit ?? 50;
  const raw: Candidate[] = [];
  for (const adapter of adapters) {
    if (adapter.costPerCall > 0) continue;
    raw.push(...adapter.search(queries, limit - raw.length));
    if (raw.length >= limit) break;
  }
  const deduped = dedupe(raw);
  const filtered = applyFilter(deduped.survivors, criteria, reachability, {
    now: config.filterNow,
  });
  if (config.store) {
    for (const c of filtered.possible) {
      if (!config.store.isSuppressed(c.id)) {
        config.store.savePossible(c);
      }
    }
  }
  const { summary: outreach } = runOutreach(filtered.possible, {
    situationType: templateName,
    criteria,
    manualApprove: config.manualApprove ?? true,
    channelOrder: [...situation.channels],
  });
  const audit = {
    stage: "complete",
    ts: new Date().toISOString(),
    situationType: templateName,
    criteriaNames: criteria.map((c) => c.name),
    sources,
    possibleCount: filtered.possible.length,
    noiseDropped: filtered.noiseDropped,
    outreach: { ...outreach },
  };
  config.store?.appendAudit(audit);
  return {
    situationType: templateName,
    criteriaNames: criteria.map((c) => c.name),
    sources,
    possible: filtered.possible,
    noiseDropped: filtered.noiseDropped,
    outreach,
    spendThisRun: 0,
  };
}

export function loadFixtureRows(
  possibleRaw: Record<string, unknown>[],
  noiseRaw: Record<string, unknown>[],
  source: string,
): Candidate[] {
  return [...possibleRaw, ...noiseRaw].map((r) => normalize(r, source));
}