import type { Candidate, Criteria, OutreachSummary } from "../models";
import { buildMessage } from "./templates";

export interface BatchMessage {
  candidateId: string;
  channel: string;
  recipient: string;
  body: string;
}

export interface OutreachBatch {
  batchId: string;
  situationType: string;
  messages: BatchMessage[];
}

export function runOutreach(
  possible: readonly Candidate[],
  options: {
    situationType: string;
    criteria: readonly Criteria[];
    manualApprove: boolean;
    channelOrder?: readonly string[];
  },
): { summary: OutreachSummary; batch: OutreachBatch } {
  const channels = options.channelOrder ?? ["email", "linkedin", "dm"];
  const messages: BatchMessage[] = [];
  for (const candidate of possible) {
    let recipient = "";
    let channel = channels[0] ?? "email";
    for (const ch of channels) {
      const v = candidate.contacts[ch];
      if (typeof v === "string" && v.trim()) {
        channel = ch;
        recipient = v.trim();
        break;
      }
    }
    messages.push({
      candidateId: candidate.id,
      channel,
      recipient,
      body: buildMessage(options.situationType, candidate, options.criteria),
    });
  }
  const batch: OutreachBatch = {
    batchId: `batch-${Date.now()}`,
    situationType: options.situationType,
    messages,
  };
  const skipped = options.manualApprove ? messages.length : 0;
  const sent = options.manualApprove ? 0 : messages.length;
  return {
    summary: { sent, replied: 0, bounced: 0, suppressed: 0, skipped },
    batch,
  };
}