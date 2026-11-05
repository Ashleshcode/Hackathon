import { describe, expect, it } from 'vitest';
import { formatDuration, requestYoutubeContext } from './youtubeContext.js';

const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

describe('requestYoutubeContext', () => {
  it('asks the local backend for the listing and keeps the face score out', async () => {
    let sent;
    const fetchImpl = async (url, options) => {
      sent = { url, options };
      return json({
        context_id: 'yt_abc',
        video_id: 'EtEvS__IoMs',
        audiovisual_analysis: 'not_performed',
        metadata: {
          title: 'Obsession',
          channel_title: 'JioHotstar',
          channel_id: 'UCaaaaaaaaaaaa',
          published_at: '2026-10-20T00:00:00Z',
          duration: 'PT1M45S',
          description: 'A trailer.',
          prediction: 'real',
          fake_score: 0,
        },
      });
    };
    const result = await requestYoutubeContext('https://youtu.be/EtEvS__IoMs?t=13', { fetchImpl, apiUrl: 'http://localhost:8000' });
    expect(sent.url).toBe('http://localhost:8000/api/youtube/context');
    expect(sent.options.method).toBe('POST');
    expect(sent.options.credentials).toBeUndefined();
    expect(JSON.parse(sent.options.body)).toEqual({ video_url: 'https://youtu.be/EtEvS__IoMs?t=13', video_id: null });
    expect(result.ok).toBe(true);
    expect(result.context.metadata).toEqual({
      title: 'Obsession',
      channel_title: 'JioHotstar',
      channel_id: 'UCaaaaaaaaaaaa',
      published_at: '2026-10-20T00:00:00Z',
      duration: 'PT1M45S',
      description: 'A trailer.',
    });
    expect(result.context.metadata.prediction).toBeUndefined();
  });

  it('reports a missing backend key without inventing a channel', async () => {
    const fetchImpl = async () => json({ detail: { code: 'youtube_connector_not_configured' } }, 503);
    const result = await requestYoutubeContext('https://www.youtube.com/watch?v=EtEvS__IoMs', { fetchImpl });
    expect(result).toEqual({ ok: false, error: 'youtube_connector_not_configured' });
  });
});

describe('formatDuration', () => {
  it('renders an ISO duration as a clock time', () => {
    expect(formatDuration('PT1M45S')).toBe('01:45');
    expect(formatDuration('PT1H2M3S')).toBe('1:02:03');
  });
});