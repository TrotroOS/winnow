export interface Candidate {
  id: string;
  name: string;
  org: string;
  role: string;
  signals: Record<string, string>;
  contacts: Record<string, string>;
  source: string;
  collectedAt: Date;
}

export interface Criteria {
  name: string;
  predicate: (candidate: Candidate, ctx?: { now?: Date }) => boolean;
  cost: number;
}

export interface StartupSituation {
  stage: string;
  product: string;
  goal: string;
  constraint: string;
  segment: string;
  channels: readonly string[];
}

export interface OutreachSummary {
  sent: number;
  replied: number;
  bounced: number;
  suppressed: number;
  skipped: number;
}

export interface RunResult {
  situationType: string;
  criteriaNames: readonly string[];
  sources: readonly string[];
  possible: readonly Candidate[];
  noiseDropped: number;
  outreach: OutreachSummary;
  enrichedCount?: number;
  backlogCount?: number;
  spendThisRun?: number;
}