// UI development fixtures only. These are not detector or graph results, and
// this is not the demo dataset. Field names follow the illustrative shapes in
// TEAM_WORK_SPLIT.md and may change at the first integration checkpoint.

const MOCK_MODEL = 'mock_detector_not_a_real_model';
const SAMPLE_LIMITATIONS = ['Mock response: no model ran on this file.'];

export const IMAGE_SCENARIOS = {
  completed: {
    label: 'Image: completed',
    response: {
      analysis_id: 'A001',
      media_type: 'image',
      model: MOCK_MODEL,
      prediction: 'fake',
      score: 0.82,
      score_type: 'model_output',
      status: 'completed',
      provenance: 'uploaded_file',
      limitations: [
        ...SAMPLE_LIMITATIONS,
        'Face-focused detector: the score covers the detected face, not the whole image.',
      ],
    },
  },
  no_face: {
    label: 'Image: no face found',
    response: {
      analysis_id: 'A002',
      media_type: 'image',
      model: MOCK_MODEL,
      prediction: null,
      score: null,
      score_type: 'model_output',
      status: 'inconclusive',
      provenance: 'uploaded_file',
      limitations: [...SAMPLE_LIMITATIONS, 'No detectable face, so no score was produced.'],
    },
  },
  error: {
    label: 'Upload fails',
    error: 'Mock error: the file could not be read as a valid image or video.',
  },
};

const frame = (timestamp_seconds, face_detected, prediction, score) => ({
  timestamp_seconds,
  face_detected,
  prediction,
  score,
});

export const VIDEO_SCENARIOS = {
  completed: {
    label: 'Video: mixed frames',
    response: {
      analysis_id: 'V001',
      media_type: 'video',
      model: MOCK_MODEL,
      frames_sampled: 10,
      frames_with_faces: 8,
      frame_results: [
        frame(0, true, 'real', 0.21),
        frame(4.2, true, 'real', 0.28),
        frame(8.4, false, null, null),
        frame(12.6, true, 'fake', 0.71),
        frame(16.8, true, 'fake', 0.76),
        frame(21, true, 'fake', 0.84),
        frame(25.2, false, null, null),
        frame(29.4, true, 'fake', 0.69),
        frame(33.6, true, 'uncertain', 0.52),
        frame(37.8, true, 'real', 0.33),
      ],
      video_assessment: 'uncertain',
      aggregation_method: 'mock_method_placeholder',
      status: 'completed',
      provenance: 'uploaded_file',
      limitations: [
        ...SAMPLE_LIMITATIONS,
        'Only sampled frames were analysed, so other parts of the video were not examined.',
      ],
    },
  },
  no_face: {
    label: 'Video: no faces found',
    response: {
      analysis_id: 'V002',
      media_type: 'video',
      model: MOCK_MODEL,
      frames_sampled: 3,
      frames_with_faces: 0,
      frame_results: [frame(0, false, null, null), frame(5, false, null, null), frame(10, false, null, null)],
      video_assessment: 'inconclusive',
      aggregation_method: 'mock_method_placeholder',
      status: 'inconclusive',
      provenance: 'uploaded_file',
      limitations: [...SAMPLE_LIMITATIONS, 'Too few usable frames to assess this video.'],
    },
  },
  error: IMAGE_SCENARIOS.error,
};

const post = (post_id, platform, account_id, time, text, media_hash = null) => ({
  post_id,
  platform,
  account_id,
  timestamp: `2026-11-05T${time}:00Z`,
  text,
  url: `https://example.invalid/post/${post_id}`,
  media_hash,
});

const REPEATED = 'Fictional sample caption repeated across several accounts.';

const SAMPLE_POSTS = [
  post('p001', 'platform_a', 'account_01', '10:00', REPEATED, 'hash_aaa'),
  post('p002', 'platform_a', 'account_02', '10:01', REPEATED, 'hash_aaa'),
  post('p003', 'platform_b', 'account_03', '10:02', REPEATED, 'hash_aaa'),
  post('p004', 'platform_b', 'account_04', '10:04', `${REPEATED} Share this.`, 'hash_aaa'),
  post('p005', 'platform_a', 'account_05', '11:15', 'A fictional local event drew a big crowd this weekend.'),
  post('p006', 'platform_b', 'account_06', '14:40', 'Went along to the fictional event and the crowd was huge.'),
  post('p007', 'platform_a', 'account_07', '18:05', 'Thoughts on the event after reading a few fictional reports.'),
  post('p008', 'platform_a', 'account_08', '09:12', 'Unrelated fictional post about a bakery.'),
  post('p009', 'platform_b', 'account_09', '13:30', 'Unrelated fictional post about a bike ride.'),
];

const account = (id, platform, cluster_id, post_count = 1) => ({
  id,
  type: 'account',
  label: id,
  account_id: id,
  platform,
  cluster_id,
  post_count,
});

const signal = (type, evidence, post_ids) => ({ type, evidence, post_ids });
const edge = (source, target, signals) => ({ id: `${source}__${target}`, source, target, signals });

const hashSignal = (a, b) => signal('same_media_hash', 'Both posts carry media hash hash_aaa.', [a, b]);
const captionSignal = (a, b, similarity) =>
  signal('similar_caption', `TF-IDF cosine similarity of ${similarity}.`, [a, b]);
const timeSignal = (a, b, minutes) =>
  signal('close_posting_time', `Posted ${minutes} min apart.`, [a, b]);

const SAMPLE_GRAPH = {
  nodes: [
    account('account_01', 'platform_a', 'cluster_1'),
    account('account_02', 'platform_a', 'cluster_1'),
    account('account_03', 'platform_b', 'cluster_1'),
    account('account_04', 'platform_b', 'cluster_1'),
    account('account_05', 'platform_a', null),
    account('account_06', 'platform_b', null),
    account('account_07', 'platform_a', null),
    account('account_08', 'platform_a', null),
    account('account_09', 'platform_b', null),
  ],
  edges: [
    edge('account_01', 'account_02', [hashSignal('p001', 'p002'), captionSignal('p001', 'p002', '1.00'), timeSignal('p001', 'p002', 1)]),
    edge('account_01', 'account_03', [hashSignal('p001', 'p003'), captionSignal('p001', 'p003', '1.00'), timeSignal('p001', 'p003', 2)]),
    edge('account_02', 'account_03', [hashSignal('p002', 'p003'), captionSignal('p002', 'p003', '1.00'), timeSignal('p002', 'p003', 1)]),
    edge('account_03', 'account_04', [hashSignal('p003', 'p004'), captionSignal('p003', 'p004', '0.87'), timeSignal('p003', 'p004', 2)]),
    edge('account_01', 'account_04', [hashSignal('p001', 'p004')]),
    edge('account_05', 'account_06', [captionSignal('p005', 'p006', '0.41')]),
  ],
  clusters: [
    {
      cluster_id: 'cluster_1',
      account_ids: ['account_01', 'account_02', 'account_03', 'account_04'],
      summary: 'Repeated media and captions, posted within 4 minutes.',
    },
  ],
};

function largeGraph() {
  const nodes = [];
  const edges = [];
  const clusters = [];
  for (let c = 0; c < 8; c += 1) {
    const ids = [];
    for (let n = 0; n < 25; n += 1) {
      const id = `account_${c}_${n}`;
      ids.push(id);
      nodes.push(account(id, n % 2 ? 'platform_b' : 'platform_a', `cluster_${c + 1}`));
      if (n > 0) {
        const target = ids[Math.floor(n / 2)];
        edges.push(edge(target, id, [signal('close_posting_time', 'Mock rendering test edge.', [])]));
      }
    }
    clusters.push({ cluster_id: `cluster_${c + 1}`, account_ids: ids, summary: 'Mock cluster for testing graph size.' });
  }
  return { nodes, edges, clusters };
}

const summary = (total_records, accepted, errors, platforms) => ({
  total_records,
  accepted,
  rejected: errors.length,
  errors,
  platforms,
});

// Fictional campaign that the extension's demo results link to.
const DEMO_CAPTION = 'Fictional demo caption repeated by several demo accounts.';
const demoAccounts = [1, 2, 3, 4, 5].map((n) => `demo_account_0${n}`);
const EXTENSION_DEMO_POSTS = [
  ...demoAccounts.map((id, index) =>
    post(`demo_p0${index + 1}`, index % 2 ? 'platform_b' : 'platform_a', id, `10:0${index * 2}`, DEMO_CAPTION, 'synthetic_demo_hash_01'),
  ),
  post('demo_p06', 'platform_a', 'demo_account_06', '15:20', 'Unrelated fictional demo post about a harbour walk.'),
];
const EXTENSION_DEMO_GRAPH = {
  nodes: [
    ...demoAccounts.map((id, index) => account(id, index % 2 ? 'platform_b' : 'platform_a', 'cluster_1')),
    account('demo_account_06', 'platform_a', null),
  ],
  edges: demoAccounts.flatMap((source, i) =>
    demoAccounts.slice(i + 1).map((target, offset) => {
      const a = `demo_p0${i + 1}`;
      const b = `demo_p0${i + offset + 2}`;
      return edge(source, target, [
        signal('same_media_hash', 'Same media hash: synthetic_demo_hash_01. Post pairs: 1.', [a, b]),
        signal('similar_caption', 'Highest TF-IDF cosine similarity: 0.94. Post pairs: 1.', [a, b]),
        signal('close_posting_time', `Posts with shared content within 10 min. Closest gap: ${(offset + 1) * 2}.0 min. Post pairs: 1.`, [a, b]),
      ]);
    }),
  ),
  clusters: [
    {
      cluster_id: 'cluster_1',
      account_ids: demoAccounts,
      signals: ['same_media_hash', 'similar_caption', 'close_posting_time'],
      summary: '5 fictional demo accounts linked by the same media, similar captions and close posting times.',
    },
  ],
};

export const CAMPAIGN_SCENARIOS = {
  C_EXT_DEMO: {
    label: 'Browser extension demo',
    campaign: {
      campaign_id: 'C_EXT_DEMO',
      status: 'completed',
      provenance: 'synthetic_demo_data',
      import_summary: summary(6, 6, [], { platform_a: 4, platform_b: 2 }),
      posts: EXTENSION_DEMO_POSTS,
    },
    graph: EXTENSION_DEMO_GRAPH,
  },
  C001: {
    label: 'Small graph, with row errors',
    campaign: {
      campaign_id: 'C001',
      status: 'completed',
      provenance: 'mock_ui_fixture',
      import_summary: summary(
        11,
        9,
        [
          { row: 4, message: 'Missing required field: account_id' },
          { row: 9, message: 'Invalid timestamp: "yesterday"' },
        ],
        { platform_a: 5, platform_b: 4 },
      ),
      posts: SAMPLE_POSTS,
    },
    graph: SAMPLE_GRAPH,
  },
  C_EMPTY: {
    label: 'No relationships found',
    campaign: {
      campaign_id: 'C_EMPTY',
      status: 'completed',
      provenance: 'mock_ui_fixture',
      import_summary: summary(0, 0, [], {}),
      posts: [],
    },
    graph: { nodes: [], edges: [], clusters: [] },
  },
  C_LARGE: {
    label: 'Large graph (200 accounts)',
    campaign: {
      campaign_id: 'C_LARGE',
      status: 'completed',
      provenance: 'mock_ui_fixture',
      import_summary: summary(200, 200, [], { platform_a: 104, platform_b: 96 }),
      posts: [],
    },
    graph: largeGraph(),
  },
};

export const MOCK_OVERVIEW = {
  media_analysed: 2,
  posts_imported: 9,
  campaigns: 1,
  investigations: 1,
  recent: [
    { id: 'R001', kind: 'Report', description: 'Sample report combining A001, V001 and C001', href: '/reports/R001' },
    { id: 'C001', kind: 'Campaign', description: '9 of 11 sample records accepted', href: '/campaigns/C001' },
  ],
};

export const MOCK_EXTENSION_REPORT = {
  report_id: 'R_EXT_DEMO',
  status: 'completed',
  provenance: 'synthetic_demo_data',
  media_findings: [
    {
      analysis_id: 'DEMO1',
      media_type: 'image',
      model: 'demo_detector_not_a_real_model',
      outcome: 'High synthetic-media risk',
      score: 0.87,
      detail: 'Fictional detector output from the browser extension demo.',
    },
  ],
  coordination_findings: [
    {
      campaign_id: 'C_EXT_DEMO',
      cluster_id: 'cluster_1',
      account_count: 5,
      signals: ['same_media_hash', 'similar_caption', 'close_posting_time'],
      detail: '5 fictional demo accounts linked by the same media, similar captions and close posting times.',
    },
  ],
  limitations: [
    'Synthetic demo data: no real analysis produced these findings.',
    'Coordination signals show observed similarity, not intent or proof of malicious activity.',
  ],
  recommended_actions: [
    'Find the original source of the media before drawing a conclusion.',
    'Check whether these accounts share a legitimate reason to post the same content.',
  ],
};

export const MOCK_REPORT = {
  report_id: 'R001',
  status: 'completed',
  provenance: 'mock_ui_fixture',
  media_findings: [
    {
      analysis_id: 'A001',
      media_type: 'image',
      model: MOCK_MODEL,
      outcome: 'fake',
      score: 0.82,
      detail: 'Detector output for one uploaded image.',
    },
    {
      analysis_id: 'V001',
      media_type: 'video',
      model: MOCK_MODEL,
      outcome: 'uncertain',
      score: null,
      detail: '10 frames sampled, 8 with faces. Higher scores between 12.6s and 29.4s.',
    },
  ],
  coordination_findings: [
    {
      campaign_id: 'C001',
      cluster_id: 'cluster_1',
      account_count: 4,
      signals: ['same_media_hash', 'similar_caption', 'close_posting_time'],
      detail: 'Repeated media and captions, posted within 4 minutes.',
    },
  ],
  limitations: [
    'Mock report: no real analysis produced these findings.',
    'Coordination signals show observed similarity, not intent or proof of malicious activity.',
    'Video findings cover sampled frames only.',
  ],
  recommended_actions: [
    'Review the frames between 12.6s and 29.4s by hand.',
    'Check whether cluster_1 accounts share a legitimate reason to repost the same media.',
    'Find the original source of the media before drawing a conclusion.',
  ],
};
