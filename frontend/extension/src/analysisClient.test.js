import { describe, expect, it } from 'vitest';
import { AnalysisError, analyzePage, buildCheckPayload, buildPayload, listCampaigns, normalizeAnalysis } from './analysisClient.js';
import { DEMO_SCENARIOS } from './demoData.js';

const valid = () => structuredClone(DEMO_SCENARIOS.signals.response);
const page = {
  url: 'https://x.com/demo/status/1',
  platform: 'x',
  content_type: 'none',
  post_text: null,
  account: null,
  timestamp: null,
  media: [],
  integration: 'pending_x_api',
  extra: 'should not be sent',
};
const youtubePage = {
  url: 'https://www.youtube.com/watch?v=abcdefghijk',
  platform: 'youtube',
  content_type: 'none',
  video_id: 'abcdefghijk',
  post_text: 'must not be sent',
  account: '@must-not-be-sent',
  timestamp: '2026-01-01T00:00:00Z',
  media: [{ type: 'video', url: 'https://example.invalid/video.mp4' }],
  integration: 'pending_youtube_metadata',
};

const jsonResponse = (body, status = 200) => new Response(JSON.stringify(body), { status });

const MEDIA_BODY = {
  analysis_id: 'E1',
  report_id: 'R1',
  limitations: ['Media limitation'],
  media: { status: 'completed', media_type: 'image', risk_level: 'high', score: 0.8, model: 'model' },
};
const CHECK_BODY = {
  campaign_id: 'C2',
  dataset: { campaign_id: 'C1', source_file: 'posts.csv', provenance: 'uploaded_dataset', post_count: 5 },
  limitations: ['Check limitation'],
  coordination: {
    status: 'signals_found',
    related_post_count: 1,
    signals: [{ type: 'similar_caption', evidence: 'With a: similar.', post_ids: ['p'], related_account: 'a' }],
  },
};

// Replies by path, and throws for paths that should not be called.
function fakeApi(routes) {
  const calls = [];
  const fetchImpl = async (url, options) => {
    const path = url.replace('http://localhost:8000', '');
    calls.push({ path, options });
    const route = routes[path];
    if (!route) return jsonResponse({ detail: 'Not found' }, 404);
    return route();
  };
  return { fetchImpl, calls };
}
const live = (fetchImpl, extra = {}) => analyzePage(youtubePage, { mode: 'live', campaignId: 'C1', fetchImpl, ...extra });
const CHECK_PATH = '/api/campaigns/C1/check-post';
const MEDIA_PATH = '/api/extension/analyze';

describe('normalizeAnalysis', () => {
  it('keeps a missing score as null, never 0', () => {
    const raw = valid();
    delete raw.media.score;
    expect(normalizeAnalysis(raw).media.score).toBeNull();
    raw.media.score = 0;
    expect(normalizeAnalysis(raw).media.score).toBe(0);
  });

  it.each([
    ['not an object', () => 'nope'],
    ['missing sections', () => ({ media: {} })],
    ['score as text', () => ({ ...valid(), media: { ...valid().media, score: '0.8' } })],
    ['score out of range', () => ({ ...valid(), media: { ...valid().media, score: 87 } })],
    ['unknown risk level', () => ({ ...valid(), media: { ...valid().media, risk_level: 'fake' } })],
    ['signal without evidence', () => ({ ...valid(), coordination: { ...valid().coordination, signals: [{ type: 'x' }] } })],
    ['negative count', () => ({ ...valid(), coordination: { ...valid().coordination, related_post_count: -1 } })],
  ])('rejects %s', (_name, build) => {
    expect(() => normalizeAnalysis(build())).toThrow(AnalysisError);
  });

  it('does not add a coordination score to the result', () => {
    expect(Object.keys(normalizeAnalysis(valid()).coordination).sort()).toEqual(['related_post_count', 'signals', 'status']);
  });
});

describe('buildPayload', () => {
  it('sends only the listed fields', () => {
    expect(Object.keys(buildPayload(page)).sort()).toEqual(['account', 'content_type', 'media', 'platform', 'post_text', 'timestamp', 'url']);
  });
});

describe('buildCheckPayload', () => {
  it('drops page text, account, time, and media', () => {
    expect(buildCheckPayload(youtubePage)).toEqual({
      url: youtubePage.url,
      platform: 'youtube',
      post_text: null,
      account: null,
      timestamp: null,
    });
  });
});

describe('demo mode', () => {
  it('makes no network request and labels results as synthetic', async () => {
    const fetchImpl = () => {
      throw new Error('demo mode must not use the network');
    };
    const result = await analyzePage(page, { mode: 'demo', demoScenario: 'signals', fetchImpl });
    expect(result.provenance).toBe('synthetic_demo_data');
  });

  it('demo error and no-score scenarios behave like the real ones', async () => {
    await expect(analyzePage(page, { mode: 'demo', demoScenario: 'malformed' })).rejects.toMatchObject({ kind: 'malformed' });
    await expect(analyzePage(page, { mode: 'demo', demoScenario: 'timeout' })).rejects.toMatchObject({ kind: 'timeout' });
    const noScore = await analyzePage(page, { mode: 'demo', demoScenario: 'no_score' });
    expect(noScore.media.score).toBeNull();
  });
});

describe('live mode', () => {
  it('compares a YouTube URL with a campaign and ignores a fake media success', async () => {
    const { fetchImpl, calls } = fakeApi({ [MEDIA_PATH]: () => jsonResponse(MEDIA_BODY), [CHECK_PATH]: () => jsonResponse(CHECK_BODY) });
    const result = await live(fetchImpl);
    expect(calls.map((call) => call.path)).toEqual([CHECK_PATH]);
    const body = JSON.parse(calls[0].options.body);
    expect(calls[0].options.credentials).toBe('omit');
    expect(body).toEqual({ url: youtubePage.url, platform: 'youtube', post_text: null, account: null, timestamp: null });
    expect(result).toMatchObject({
      provenance: 'live',
      campaign_id: 'C2',
      report_id: null,
      status: 'completed',
      media: { status: 'not_available', score: null },
    });
    expect(result.limitations[0]).toContain('/api/extension/analyze was not called');
    expect(result.limitations.some((item) => item.includes('does not call YouTube or score the video'))).toBe(true);
  });

  it('does not call the missing media route when no campaign is selected', async () => {
    const { fetchImpl, calls } = fakeApi({ [MEDIA_PATH]: () => jsonResponse(MEDIA_BODY) });
    await expect(live(fetchImpl, { campaignId: null })).rejects.toMatchObject({ kind: 'nothing_available' });
    expect(calls).toHaveLength(0);
  });

  it('does not turn a failed campaign check into a media score', async () => {
    const { fetchImpl, calls } = fakeApi({ [MEDIA_PATH]: () => jsonResponse(MEDIA_BODY), [CHECK_PATH]: () => jsonResponse({}, 500) });
    await expect(live(fetchImpl)).rejects.toMatchObject({ kind: 'server' });
    expect(calls.map((call) => call.path)).toEqual([CHECK_PATH]);
  });

  it('does not read an X page or call the API for it', async () => {
    const { fetchImpl, calls } = fakeApi({ [MEDIA_PATH]: () => jsonResponse(MEDIA_BODY), [CHECK_PATH]: () => jsonResponse(CHECK_BODY) });
    await expect(analyzePage(page, { mode: 'live', campaignId: 'C1', fetchImpl })).rejects.toMatchObject({ kind: 'integration_pending' });
    expect(calls).toHaveLength(0);
  });

  it('calls no result insufficient only when there is really nothing', async () => {
    const none = { ...CHECK_BODY, coordination: { status: 'none_found', related_post_count: 0, signals: [] } };
    const { fetchImpl } = fakeApi({ [CHECK_PATH]: () => jsonResponse(none) });
    expect((await live(fetchImpl)).status).toBe('insufficient_evidence');
  });

  it('fails clearly when nothing could run', async () => {
    const empty = fakeApi({});
    await expect(live(empty.fetchImpl, { campaignId: null })).rejects.toMatchObject({ kind: 'nothing_available' });
    await expect(live(empty.fetchImpl)).rejects.toMatchObject({ kind: 'not_found' });
    const down = async () => {
      throw new TypeError('network');
    };
    await expect(live(down)).rejects.toMatchObject({ kind: 'unavailable' });
    await expect(live(down, { campaignId: null })).rejects.toMatchObject({ kind: 'nothing_available' });
  });

  it('rejects malformed responses and handles timeouts', async () => {
    const badJson = fakeApi({ [CHECK_PATH]: () => new Response('<html>') });
    await expect(live(badJson.fetchImpl)).rejects.toMatchObject({ kind: 'malformed' });
    const badShape = fakeApi({ [CHECK_PATH]: () => jsonResponse({ coordination: { status: 'proven' } }) });
    await expect(live(badShape.fetchImpl)).rejects.toMatchObject({ kind: 'malformed' });
    const hang = (_url, { signal }) =>
      new Promise((_resolve, reject) => {
        signal.addEventListener('abort', () => reject(Object.assign(new Error('aborted'), { name: 'AbortError' })));
      });
    await expect(live(hang, { timeoutMs: 10 })).rejects.toMatchObject({ kind: 'timeout' });
  });
});

describe('listCampaigns', () => {
  it('returns campaigns and rejects unexpected data', async () => {
    const good = fakeApi({ '/api/campaigns': () => jsonResponse([{ campaign_id: 'C1' }]) });
    expect(await listCampaigns({ fetchImpl: good.fetchImpl })).toEqual([{ campaign_id: 'C1' }]);
    const bad = fakeApi({ '/api/campaigns': () => jsonResponse({ nope: true }) });
    await expect(listCampaigns({ fetchImpl: bad.fetchImpl })).rejects.toMatchObject({ kind: 'malformed' });
  });
});
