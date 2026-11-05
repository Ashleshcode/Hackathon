// The boundary between the popup and the backend. Contracts: extension/README.md.
import { API_URL, ANALYZE_TIMEOUT_MS } from './config.js';
import { DEMO_SCENARIOS } from './demoData.js';

const DEMO_DELAY_MS = 900;
const RISK_LEVELS = ['high', 'medium', 'low'];
const MEDIA_STATUSES = ['completed', 'inconclusive', 'no_media', 'unsupported', 'not_available'];
const COORDINATION_STATUSES = ['signals_found', 'none_found', 'not_checked'];

export class AnalysisError extends Error {
  constructor(kind, message) {
    super(message);
    this.kind = kind;
  }
}

const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const isOptionalString = (value) => value === undefined || value === null || typeof value === 'string';
const optionalInList = (value, list) => value === undefined || value === null || list.includes(value);

function malformed() {
  return new AnalysisError('malformed', 'Unable to analyze this page. The Veritas API returned an unreadable response.');
}

// Reject anything outside the contract rather than guessing. A missing score
// stays null and is never replaced with a number.
function normalizeMedia(media) {
  if (!isObject(media)) throw malformed();
  const score = media.score ?? null;
  if (score !== null && (typeof score !== 'number' || !Number.isFinite(score) || score < 0 || score > 1)) throw malformed();
  if (!MEDIA_STATUSES.includes(media.status) || !optionalInList(media.risk_level, RISK_LEVELS)) throw malformed();
  if (!isOptionalString(media.model)) throw malformed();
  return {
    status: media.status,
    media_type: media.media_type ?? null,
    risk_level: media.risk_level ?? null,
    score,
    score_type: media.score_type ?? 'model_output',
    model: media.model ?? null,
  };
}

function normalizeCoordination(coordination) {
  if (!isObject(coordination) || !COORDINATION_STATUSES.includes(coordination.status)) throw malformed();
  const signals = coordination.signals ?? [];
  const validSignal = (signal) => isObject(signal) && typeof signal.type === 'string' && typeof signal.evidence === 'string';
  if (!Array.isArray(signals) || !signals.every(validSignal)) throw malformed();
  const count = coordination.related_post_count ?? null;
  if (count !== null && (!Number.isInteger(count) || count < 0)) throw malformed();
  return { status: coordination.status, related_post_count: count, signals };
}

function normalizeLimitations(limitations) {
  const items = limitations ?? [];
  if (!Array.isArray(items) || !items.every((item) => typeof item === 'string')) throw malformed();
  return items;
}

export function normalizeAnalysis(raw) {
  if (!isObject(raw)) throw malformed();
  if (![raw.analysis_id, raw.campaign_id, raw.report_id, raw.provenance].every(isOptionalString)) throw malformed();
  return {
    analysis_id: raw.analysis_id ?? null,
    status: raw.status ?? null,
    provenance: raw.provenance ?? null,
    campaign_id: raw.campaign_id ?? null,
    report_id: raw.report_id ?? null,
    limitations: normalizeLimitations(raw.limitations),
    media: normalizeMedia(raw.media),
    coordination: normalizeCoordination(raw.coordination),
    dataset: isObject(raw.dataset) ? raw.dataset : null,
  };
}

// Fields the popup may show locally. Live requests use buildCheckPayload instead.
export function buildPayload(page) {
  return {
    url: page.url,
    platform: page.platform,
    content_type: page.content_type,
    post_text: page.post_text,
    account: page.account,
    timestamp: page.timestamp,
    media: page.media,
  };
}

// Sent to the campaign check only. Page text and media are never included.
export function buildCheckPayload(page) {
  return {
    url: page.url,
    platform: page.platform,
    post_text: null,
    account: null,
    timestamp: null,
  };
}

async function request(path, { fetchImpl, timeoutMs, body }) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    let response;
    try {
      response = await fetchImpl(`${API_URL}${path}`, {
        credentials: 'omit',
        signal: controller.signal,
        ...(body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {}),
      });
    } catch (error) {
      if (error.name === 'AbortError') {
        throw new AnalysisError('timeout', 'Unable to analyze this page. The Veritas API took too long to respond.');
      }
      throw new AnalysisError('unavailable', 'Unable to analyze this page. The Veritas API could not be reached.');
    }
    if (response.status === 404) throw new AnalysisError('not_found', 'Unable to analyze this page. The requested Veritas API or campaign was not found.');
    if (!response.ok) throw new AnalysisError('server', `Unable to analyze this page. The Veritas API returned status ${response.status}.`);
    try {
      return await response.json();
    } catch {
      throw malformed();
    }
  } finally {
    clearTimeout(timer);
  }
}

// Campaigns a post can be compared against. Throws if the API can't be reached.
export async function listCampaigns({ fetchImpl = fetch, timeoutMs = 5000 } = {}) {
  const campaigns = await request('/api/campaigns', { fetchImpl, timeoutMs });
  if (!Array.isArray(campaigns) || !campaigns.every((item) => isObject(item) && typeof item.campaign_id === 'string')) throw malformed();
  return campaigns;
}

async function analyzeDemo(scenarioKey) {
  const scenario = DEMO_SCENARIOS[scenarioKey] ?? DEMO_SCENARIOS.signals;
  await new Promise((resolve) => setTimeout(resolve, DEMO_DELAY_MS));
  if (scenario.error) throw new AnalysisError(scenario.error.kind, scenario.error.message);
  return normalizeAnalysis(structuredClone(scenario.response));
}

const NOT_AVAILABLE_MEDIA = { status: 'not_available', media_type: null, risk_level: null, score: null, model: null };

const X_PENDING = 'X investigation is pending. This extension does not read X pages. It will use the official X API connector when that backend route exists.';
const INSTAGRAM_REMOVED = 'Instagram page extraction has been removed. This extension does not read Instagram pages.';

function assertLiveTarget(page) {
  if (page?.integration === 'pending_x_api' || page?.platform === 'x') {
    throw new AnalysisError('integration_pending', X_PENDING);
  }
  if (page?.integration === 'instagram_removed' || page?.platform === 'instagram') {
    throw new AnalysisError('integration_pending', INSTAGRAM_REMOVED);
  }
  if (page?.platform !== 'youtube' || !page.video_id) {
    throw new AnalysisError('integration_pending', 'Only an explicitly selected YouTube video URL can be compared. No other page content is read.');
  }
}

// Live mode calls the campaign check only. /api/extension/analyze is not a registered route.
async function analyzeLive(page, { fetchImpl, timeoutMs, campaignId }) {
  assertLiveTarget(page);
  if (!campaignId) {
    throw new AnalysisError(
      'nothing_available',
      'Select a campaign to compare this YouTube URL. This comparison does not score the video.',
    );
  }
  const coordinationBody = await request(`/api/campaigns/${encodeURIComponent(campaignId)}/check-post`, {
    fetchImpl,
    timeoutMs,
    body: buildCheckPayload(page),
  });
  const coordination = normalizeCoordination(coordinationBody.coordination);
  return normalizeAnalysis({
    analysis_id: null,
    status: coordination.status === 'signals_found' ? 'completed' : 'insufficient_evidence',
    provenance: 'live',
    campaign_id: coordinationBody.campaign_id ?? null,
    report_id: null,
    limitations: [
      'Media analysis is not connected. /api/extension/analyze was not called.',
      'This comparison does not call YouTube or score the video.',
      ...normalizeLimitations(coordinationBody.limitations),
    ],
    media: NOT_AVAILABLE_MEDIA,
    coordination,
    dataset: isObject(coordinationBody.dataset) ? coordinationBody.dataset : null,
  });
}

export function analyzePage(page, { mode, demoScenario, campaignId = null, fetchImpl = fetch, timeoutMs = ANALYZE_TIMEOUT_MS }) {
  if (mode !== 'live') return analyzeDemo(demoScenario);
  return analyzeLive(page, { fetchImpl, timeoutMs, campaignId });
}
