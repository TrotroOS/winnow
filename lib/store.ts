import type { Candidate } from "./models";

export type CandidateStatus = "possible" | "contacted" | "replied" | "bounced" | "opted_out";

export interface AuditEntry {
  stage: string;
  ts: string;
  situationType: string;
  criteriaNames: string[];
  sources: string[];
  possibleCount: number;
  noiseDropped: number;
  outreach: Record<string, number>;
}

/** In-memory operator memory for demo runs (no goodness numbers). */
export class WinnowStore {
  private possible = new Map<string, Candidate>();
  private suppressed = new Set<string>();
  private auditLog: AuditEntry[] = [];

  savePossible(candidate: Candidate): void {
    this.possible.set(candidate.id, candidate);
  }

  listPossible(): Candidate[] {
    return [...this.possible.values()];
  }

  suppress(candidateId: string): void {
    this.suppressed.add(candidateId);
  }

  isSuppressed(candidateId: string): boolean {
    return this.suppressed.has(candidateId);
  }

  appendAudit(entry: AuditEntry): void {
    this.auditLog.push(entry);
  }

  auditEntries(): readonly AuditEntry[] {
    return this.auditLog;
  }

  clear(): void {
    this.possible.clear();
    this.suppressed.clear();
    this.auditLog.length = 0;
  }
}