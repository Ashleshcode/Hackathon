import { describe, expect, it } from 'vitest';
import { formatScore, formatSeconds, formatTimestamp, safeUrl } from './format.js';
import { clusterColor, hideUnlinked, platformShapes, toElements, UNCLUSTERED_COLOR } from './graphElements.js';
import { overviewFromCampaigns } from './api.js';
import { CAMPAIGN_SCENARIOS } from './mockData.js';

describe('overviewFromCampaigns', () => {
  it('counts campaigns and leaves unknown counts empty rather than 0', () => {
    const overview = overviewFromCampaigns([
      { campaign_id: 'C2', source_file: 'b.csv', provenance: 'uploaded_dataset', post_count: 3 },
      { campaign_id: 'C1', source_file: 'a.csv', provenance: 'synthetic_demo_data', post_count: 34 },
    ]);
    expect(overview).toMatchObject({ campaigns: 2, posts_imported: 37, media_analysed: null, investigations: null });
    expect(overview.recent[0]).toMatchObject({ id: 'C2', href: '/campaigns/C2' });
    expect(overviewFromCampaigns([])).toMatchObject({ campaigns: 0, posts_imported: 0, recent: [] });
  });
});

describe('formatScore', () => {
  it('shows a missing score as missing, never as zero', () => {
    expect(formatScore(null)).toBe('No score');
    expect(formatScore(undefined)).toBe('No score');
    expect(formatScore(0)).toBe('0.00');
  });
});

describe('formatSeconds', () => {
  it('formats minutes and seconds', () => {
    expect(formatSeconds(4.2)).toBe('0:04.2');
    expect(formatSeconds(75)).toBe('1:15.0');
  });
});

describe('formatTimestamp', () => {
  it('never shows a missing time as 1970', () => {
    expect(formatTimestamp(null)).toBe('Not available');
    expect(formatTimestamp('2026-11-05T10:00:00Z')).toBe('2026-11-05 10:00 UTC');
  });
});

describe('safeUrl', () => {
  it('allows http and https only', () => {
    expect(safeUrl('https://example.invalid/post/p001')).toBe('https://example.invalid/post/p001');
    expect(safeUrl('javascript:alert(1)')).toBeNull();
    expect(safeUrl('not a url')).toBeNull();
    expect(safeUrl(null)).toBeNull();
  });
});

describe('toElements', () => {
  it('handles empty and missing graphs', () => {
    expect(toElements({ nodes: [], edges: [], clusters: [] }).elements).toEqual([]);
    expect(toElements(undefined).elements).toEqual([]);
  });

  it('converts the small and large fixtures without dropping edges', () => {
    for (const id of ['C001', 'C_LARGE']) {
      const { graph } = CAMPAIGN_SCENARIOS[id];
      const { elements, droppedEdges } = toElements(graph);
      expect(elements).toHaveLength(graph.nodes.length + graph.edges.length);
      expect(droppedEdges).toBe(0);
    }
  });

  it('drops and counts edges that point at unknown nodes', () => {
    const graph = {
      nodes: [{ id: 'a' }],
      edges: [{ id: 'a__missing', source: 'a', target: 'missing', signals: [] }],
    };
    const { elements, droppedEdges } = toElements(graph);
    expect(elements).toHaveLength(1);
    expect(droppedEdges).toBe(1);
  });

  it('every mock edge carries evidence', () => {
    for (const edge of CAMPAIGN_SCENARIOS.C001.graph.edges) {
      expect(edge.signals.length).toBeGreaterThan(0);
      edge.signals.forEach((signal) => expect(signal.evidence).toBeTruthy());
    }
  });
});

describe('hideUnlinked', () => {
  const nodes = [{ id: 'a' }, { id: 'b' }, { id: 'c' }];

  it('hides and counts accounts with no relationships', () => {
    const result = hideUnlinked({ nodes, edges: [{ id: 'e', source: 'a', target: 'b' }] });
    expect(result.graph.nodes.map((node) => node.id)).toEqual(['a', 'b']);
    expect(result.hiddenCount).toBe(1);
  });

  it('always keeps the post checked from the extension visible', () => {
    const checked = [{ id: 'a' }, { id: 'b' }, { id: 'c', is_checked_post: true }];
    const result = hideUnlinked({ nodes: checked, edges: [{ id: 'e', source: 'a', target: 'b' }] });
    expect(result.graph.nodes.map((node) => node.id)).toEqual(['a', 'b', 'c']);
    expect(toElements(result.graph).elements[2].data.checked).toBe(true);
  });

  it('keeps every account when nothing is linked', () => {
    const result = hideUnlinked({ nodes, edges: [] });
    expect(result.graph.nodes).toHaveLength(3);
    expect(result.hiddenCount).toBe(0);
  });
});

describe('platformShapes', () => {
  it('gives each platform its own shape, whatever it is called', () => {
    const nodes = [{ platform: 'zeta' }, { platform: 'alpha' }, { platform: 'zeta' }];
    expect(platformShapes(nodes)).toEqual([
      { platform: 'alpha', shape: 'ellipse' },
      { platform: 'zeta', shape: 'round-rectangle' },
    ]);
    const { elements } = toElements({ nodes: [{ id: 'a', platform: 'zeta' }, { id: 'b', platform: 'alpha' }] });
    expect(elements[0].data.platformShape).toBe('round-rectangle');
  });
});

describe('clusterColor', () => {
  it('uses the neutral colour for accounts outside any cluster', () => {
    expect(clusterColor(null, [{ cluster_id: 'cluster_1' }])).toBe(UNCLUSTERED_COLOR);
  });
});
