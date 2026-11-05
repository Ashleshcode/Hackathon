// Fictional sample responses. They aren't produced from the page being viewed.
const DEMO_LIMITATIONS = [
  'Synthetic demo data: this sample was not produced from the current page.',
  'Coordination signals show observed similarity, not intent.',
];

const DEMO_SIGNALS = [
  {
    type: 'same_media_hash',
    evidence: 'Same media hash: synthetic_demo_hash_01. Post pairs: 4.',
    post_ids: ['demo_p01', 'demo_p02', 'demo_p03', 'demo_p04', 'demo_p05'],
  },
  {
    type: 'similar_caption',
    evidence: 'Highest TF-IDF cosine similarity: 0.94. Post pairs: 4.',
    post_ids: ['demo_p01', 'demo_p02', 'demo_p03', 'demo_p04', 'demo_p05'],
  },
  {
    type: 'close_posting_time',
    evidence: 'Posts with shared content within 10 min. Closest gap: 1.0 min. Post pairs: 4.',
    post_ids: ['demo_p01', 'demo_p02', 'demo_p03', 'demo_p04', 'demo_p05'],
  },
];

const base = {
  provenance: 'synthetic_demo_data',
  campaign_id: 'C_EXT_DEMO',
  report_id: 'R_EXT_DEMO',
  limitations: DEMO_LIMITATIONS,
};

const media = (overrides) => ({
  status: 'completed',
  media_type: 'image',
  risk_level: null,
  score: null,
  score_type: 'model_output',
  model: 'demo_detector_not_a_real_model',
  ...overrides,
});

const signalsFound = { status: 'signals_found', related_post_count: 4, signals: DEMO_SIGNALS };
const noneFound = { status: 'none_found', related_post_count: 0, signals: [] };

export const DEMO_SCENARIOS = {
  signals: {
    label: 'Signals found',
    response: {
      ...base,
      analysis_id: 'DEMO1',
      status: 'completed',
      media: media({ risk_level: 'high', score: 0.87 }),
      coordination: signalsFound,
    },
  },
  no_score: {
    label: 'Detector returns no score',
    response: {
      ...base,
      analysis_id: 'DEMO2',
      status: 'inconclusive',
      media: media({ status: 'inconclusive' }),
      coordination: signalsFound,
    },
  },
  no_related: {
    label: 'No related content',
    response: {
      ...base,
      analysis_id: 'DEMO3',
      status: 'completed',
      campaign_id: null,
      report_id: null,
      media: media({ risk_level: 'low', score: 0.14 }),
      coordination: noneFound,
    },
  },
  insufficient: {
    label: 'No media, nothing related',
    response: {
      ...base,
      analysis_id: 'DEMO4',
      status: 'insufficient_evidence',
      campaign_id: null,
      report_id: null,
      media: media({ status: 'no_media', media_type: null, model: null }),
      coordination: noneFound,
    },
  },
  malformed: {
    label: 'Malformed API response',
    response: { analysis_id: 'DEMO5', media: 'not valid' },
  },
  unavailable: {
    label: 'API unavailable',
    error: { kind: 'unavailable', message: 'Unable to analyze this page. The Veritas API could not be reached.' },
  },
  timeout: {
    label: 'Backend timeout',
    error: { kind: 'timeout', message: 'Unable to analyze this page. The Veritas API took too long to respond.' },
  },
};
