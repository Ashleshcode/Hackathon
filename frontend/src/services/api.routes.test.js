import { describe, expect, it, vi } from 'vitest';
import { analyzeMedia, fetchOverview, getReport, MEDIA_ANALYSIS_PENDING, REPORTS_PENDING } from './api.js';

describe('unsupported routes', () => {
  it('does not accept a successful image analysis response', async () => {
    const opened = [];
    vi.stubGlobal(
      'XMLHttpRequest',
      class {
        open(_method, url) {
          opened.push(url);
        }

        send() {
          this.status = 200;
          this.responseText = JSON.stringify({ prediction: 'fake', score: 0.99 });
          this.onload();
        }
      },
    );
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ score: 0.99 }), { status: 200 })));

    await expect(analyzeMedia({ type: 'image/jpeg', name: 'face.jpg' })).rejects.toMatchObject({
      code: 'integration_pending',
      message: MEDIA_ANALYSIS_PENDING,
    });
    await expect(analyzeMedia({ type: 'video/mp4', name: 'clip.mp4' })).rejects.toMatchObject({ code: 'integration_pending' });
    expect(opened).toEqual([]);
    expect(fetch).not.toHaveBeenCalled();
  });

  it('does not accept a successful report response', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ report_id: 'R001', status: 'completed' }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    await expect(getReport('R001')).rejects.toMatchObject({ code: 'integration_pending', message: REPORTS_PENDING });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('builds the overview from campaigns and ignores a fake overview payload', async () => {
    const calls = [];
    const overview = await fetchOverview(async (path) => {
      calls.push(path);
      if (path === '/api/overview') {
        return { media_analysed: 9, posts_imported: 9, campaigns: 1, investigations: 4, recent: [] };
      }
      if (path === '/api/campaigns') {
        return [{ campaign_id: 'C9', source_file: 'posts.csv', provenance: 'uploaded_dataset', post_count: 3 }];
      }
      throw new Error(`unexpected ${path}`);
    });
    expect(calls).toEqual(['/api/campaigns']);
    expect(overview).toMatchObject({ media_analysed: null, investigations: null, campaigns: 1, posts_imported: 3 });
  });
});
