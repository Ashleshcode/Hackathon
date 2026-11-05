// The only module that talks to the backend. Mocks are on unless
// VITE_USE_MOCKS=false, so the UI can be built before the APIs exist.
import { CAMPAIGN_SCENARIOS } from './mockData.js';

export class IntegrationPendingError extends Error {
  constructor(message) {
    super(message);
    this.name = 'IntegrationPendingError';
    this.code = 'integration_pending';
  }
}

export const MEDIA_ANALYSIS_PENDING = 'Media upload stays disabled in this dashboard. The analysis routes are a backend test interface, not the product upload flow.';
export const REPORTS_PENDING = 'Investigation reports stay disabled in this dashboard. A stored analysis is available from the backend report route, not from this screen.';

export const USE_MOCKS = import.meta.env?.VITE_USE_MOCKS !== 'false';

const MOCK_DELAY_MS = 700;

function mockResponse(value, delay = 150) {
  return new Promise((resolve) => setTimeout(() => resolve(structuredClone(value)), delay));
}

async function mockUpload(scenario, onProgress) {
  for (const percent of [25, 60, 100]) {
    await mockResponse(null, MOCK_DELAY_MS / 3);
    onProgress?.(percent);
  }
  await mockResponse(null, MOCK_DELAY_MS);
  if (scenario.error) throw new Error(scenario.error);
  return structuredClone(scenario.response);
}

function errorMessage(body, status) {
  // The dev proxy answers with an empty 500 when the backend isn't running.
  if (status >= 500 && !body) return 'Could not reach the backend. Check that it is running.';
  try {
    const parsed = JSON.parse(body);
    if (typeof parsed.detail === 'string') return parsed.detail;
    if (typeof parsed.error === 'string') return parsed.error;
  } catch {
    // Not JSON, so fall through to the generic message.
  }
  return `Request failed with status ${status}.`;
}

async function getJson(path) {
  let response;
  try {
    response = await fetch(path);
  } catch {
    throw new Error('Could not reach the backend.');
  }
  const body = await response.text();
  if (!response.ok) {
    throw Object.assign(new Error(errorMessage(body, response.status)), { status: response.status });
  }
  return JSON.parse(body);
}

// Uses XMLHttpRequest because fetch cannot report upload progress.
function postForm(path, fields, onProgress) {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    Object.entries(fields).forEach(([key, value]) => form.append(key, value));
    const xhr = new XMLHttpRequest();
    xhr.open('POST', path);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress?.(Math.round((event.loaded / event.total) * 100));
    };
    xhr.onerror = () => reject(new Error('Could not reach the backend.'));
    xhr.onload = () => {
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new Error(errorMessage(xhr.responseText, xhr.status)));
        return;
      }
      try {
        resolve(JSON.parse(xhr.responseText));
      } catch {
        reject(new Error('The backend returned an unreadable response.'));
      }
    };
    xhr.send(form);
  });
}

export function analyzeMedia() {
  return Promise.reject(new IntegrationPendingError(MEDIA_ANALYSIS_PENDING));
}

export function importCampaign(file, sourceType, { onProgress, mockScenario = 'C001' } = {}) {
  if (USE_MOCKS) {
    return mockUpload({ response: CAMPAIGN_SCENARIOS[mockScenario].campaign }, onProgress);
  }
  return postForm('/api/campaigns/import', { file, source_type: sourceType }, onProgress);
}

function mockCampaign(id) {
  const scenario = CAMPAIGN_SCENARIOS[id];
  if (!scenario) throw new Error(`Campaign ${id} was not found.`);
  return scenario;
}

export async function getCampaign(id) {
  if (USE_MOCKS) return mockResponse(mockCampaign(id).campaign);
  return getJson(`/api/campaigns/${encodeURIComponent(id)}`);
}

export async function getCampaignGraph(id) {
  if (USE_MOCKS) return mockResponse(mockCampaign(id).graph);
  return getJson(`/api/campaigns/${encodeURIComponent(id)}/graph`);
}

export function getReport() {
  return Promise.reject(new IntegrationPendingError(REPORTS_PENDING));
}

function campaignSummaries(campaigns) {
  return campaigns
    .filter((campaign) => campaign && !campaign.parent_campaign_id)
    .map((campaign) => ({
      campaign_id: campaign.campaign_id,
      source_file: campaign.source_file ?? null,
      provenance: campaign.provenance,
      post_count: Array.isArray(campaign.posts) ? campaign.posts.length : 0,
    }));
}

// Builds what can be known from campaigns alone. Media and investigation counts
// stay null, shown as unavailable, because no API reports them yet.
export function overviewFromCampaigns(campaigns) {
  return {
    media_analysed: null,
    posts_imported: campaigns.reduce((total, campaign) => total + campaign.post_count, 0),
    campaigns: campaigns.length,
    investigations: null,
    recent: campaigns.slice(0, 5).map((campaign) => ({
      id: campaign.campaign_id,
      kind: 'Campaign',
      description: `${campaign.source_file ?? 'Imported dataset'}: ${campaign.post_count} posts (${campaign.provenance})`,
      href: `/campaigns/${encodeURIComponent(campaign.campaign_id)}`,
    })),
  };
}

// /api/overview is not registered. Counts come from the campaign list.
// Media and investigation totals stay null instead of a fabricated number.
export async function fetchOverview(getJsonImpl = getJson) {
  return overviewFromCampaigns(await getJsonImpl('/api/campaigns'));
}

export async function getOverview() {
  if (USE_MOCKS) {
    const campaigns = campaignSummaries(Object.values(CAMPAIGN_SCENARIOS).map((scenario) => scenario.campaign));
    return mockResponse(overviewFromCampaigns(campaigns));
  }
  return fetchOverview();
}

export async function listDisseminationCases() {
  if (USE_MOCKS) return { cases: [] };
  return { cases: await getJson('/api/dissemination/cases') };
}

export function getDisseminationCase(caseId) {
  if (USE_MOCKS) return Promise.resolve(null);
  return getJson(`/api/dissemination/cases/${encodeURIComponent(caseId)}`);
}

export function getDisseminationGraph(caseId) {
  if (USE_MOCKS) return Promise.resolve(null);
  return getJson(`/api/dissemination/cases/${encodeURIComponent(caseId)}/graph`);
}
