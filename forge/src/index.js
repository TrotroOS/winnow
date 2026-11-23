import { invokeRemote } from '@forge/api';

const STUB_SITUATION_TYPE = 'launch';
const STUB_CRITERIA = ['has_org'];

function stubDescribe(situation) {
  return {
    binary_only: true,
    mode: 'stub',
    situation_input: situation,
    situation_type: parseStubSituation(situation),
    criteria_names: [...STUB_CRITERIA],
    note: 'Configure WINNOW_API_BASE_URL and deploy Python http_server for live runs.',
  };
}

function stubRun(situation) {
  const situationType = parseStubSituation(situation);
  return {
    binary_only: true,
    mode: 'stub',
    situation_type: situationType,
    criteria_names: [...STUB_CRITERIA],
    sources: ['fixture_primary'],
    possible_count: 1,
    noise_dropped: 1,
    outreach: { sent: 1, replied: 0, bounced: 0, suppressed: 0, skipped: 0 },
    audit_summary: {
      timestamp: new Date().toISOString(),
      possible_refs: [
        {
          id: 'demo-1',
          name: 'Avery Chen',
          org: 'Northwind Labs',
          source: 'fixture_primary',
        },
      ],
    },
  };
}

function parseStubSituation(situation) {
  const text = (situation || '').trim();
  return text.length > 0 ? text.slice(0, 80) : STUB_SITUATION_TYPE;
}

function useLiveApi() {
  const base = process.env.WINNOW_API_BASE_URL || '';
  return Boolean(base) && !base.includes('winnow-api.invalid');
}

function useStub(reason) {
  console.log(`Winnow Forge using stub: ${reason}`);
}

async function postJson(path, body) {
  const response = await invokeRemote('winnow-api', {
    path,
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Winnow API ${response.status}: ${detail}`);
  }
  return response.json();
}

export async function describeSituation(payload) {
  const situation = payload?.situation ?? '';
  if (!useLiveApi()) {
    useStub('WINNOW_API_BASE_URL not set');
    return stubDescribe(situation);
  }
  try {
    const data = await postJson('/v1/describe', { situation });
    return { ...data, mode: 'live' };
  } catch (err) {
    console.error(err);
    useStub('describe API failed');
    return stubDescribe(situation);
  }
}

export async function triggerWinnowRun(payload) {
  const situation = payload?.situation ?? '';
  if (!useLiveApi()) {
    useStub('WINNOW_API_BASE_URL not set');
    return stubRun(situation);
  }
  try {
    const data = await postJson('/v1/run', { situation });
    return { ...data, mode: 'live' };
  } catch (err) {
    console.error(err);
    useStub('run API failed');
    return stubRun(situation);
  }
}

export function handler() {
  return {
    binary_only: true,
    api_configured: useLiveApi(),
  };
}