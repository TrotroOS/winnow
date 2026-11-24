import type { Candidate } from "../models";

export interface SourceAdapter {
  readonly name: string;
  readonly costPerCall: number;
  search(queries: readonly string[], limit: number): Candidate[];
}