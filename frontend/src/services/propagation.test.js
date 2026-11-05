import { describe, expect, it, vi } from 'vitest';
import { listDisseminationCases } from './api.js';
import { delayLabel, toPropagationElements } from './propagationElements.js';

describe('historical propagation', () => {
  it('does not call the API or invent posts while demo mode is on', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    await expect(listDisseminationCases()).resolves.toEqual({ cases: [] });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('keeps the arrow pointing from parent to child and leaves missing text empty', () => {
    const graph = {
      nodes: [
        { tweet_id: '100', user_id: '10', is_root: true, depth: 0, post_time_delay_minutes: 0, text: 'Source only' },
        { tweet_id: '101', user_id: '11', is_root: false, depth: 1, post_time_delay_minutes: 2.5, text: null },
      ],
      edges: [
        {
          id: '100->101',
          source: '100',
          target: '101',
          parent_delay_minutes: 0,
          child_delay_minutes: 2.5,
        },
      ],
    };
    const { elements, rootIds } = toPropagationElements(graph);
    const edge = elements.find((element) => element.group === 'edges');
    const child = elements.find((element) => element.data.id === '101');
    expect(edge.data.source).toBe('100');
    expect(edge.data.target).toBe('101');
    expect(edge.data.relationship).toBe('propagation_parent_to_child');
    expect(child.data.text).toBeNull();
    expect(rootIds).toEqual(['100']);
    expect(delayLabel(2.5)).toBe('2.5 min from source');
    expect(delayLabel(null)).toBe('Delay not recorded');
  });
});
