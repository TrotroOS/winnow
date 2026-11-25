import type { SourceAdapter } from "./adapter";

const adapters = new Map<string, SourceAdapter>();

export function register(adapter: SourceAdapter): void {
  adapters.set(adapter.name, adapter);
}

export function listAdapters(): SourceAdapter[] {
  return [...adapters.values()];
}

export function clear(): void {
  adapters.clear();
}