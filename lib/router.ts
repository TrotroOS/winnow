import type { Criteria, StartupSituation } from "./models";
import { listAdapters } from "./sources/registry";

export function route(
  _situation: StartupSituation,
  _criteria: readonly Criteria[],
) {
  void _situation;
  void _criteria;
  return [...listAdapters()].sort(
    (a, b) => a.costPerCall - b.costPerCall || a.name.localeCompare(b.name),
  );
}