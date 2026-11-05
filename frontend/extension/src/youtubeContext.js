// Asks the local backend for one video's public listing.
// The extension does not call googleapis.com, and this result is not a face score.

import { API_URL } from './config.js';

const METADATA_KEYS = ['title', 'channel_title', 'channel_id', 'published_at', 'duration', 'description'];

export function formatDuration(value) {
  if (typeof value !== 'string') return null;
  const match = value.match(/^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$/);
  if (!match) return value;
  const hours = Number(match[1] ?? 0);
  const minutes = Number(match[2] ?? 0);
  const seconds = Number(match[3] ?? 0);
  const clock = [minutes, seconds].map((part) => String(part).padStart(2, '0'));
  if (hours) clock.unshift(String(hours));
  return clock.join(':');
}

function allowedMetadata(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const metadata = {};
  for (const key of METADATA_KEYS) {
    metadata[key] = typeof value[key] === 'string' ? value[key] : null;
  }
  return metadata;
}

export async function requestYoutubeContext(videoUrl, { fetchImpl = fetch, apiUrl = API_URL, timeoutMs = 20000 } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    let response;
    try {
      response = await fetchImpl(`${apiUrl}/api/youtube/context`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ video_url: videoUrl, video_id: null }),
        signal: controller.signal,
      });
    } catch (error) {
      if (error?.name === 'AbortError') return { ok: false, error: 'timeout' };
      return { ok: false, error: 'unavailable' };
    }
    let payload = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
    if (!response.ok) {
      const code = payload?.detail?.code;
      return { ok: false, error: typeof code === 'string' ? code : 'rejected' };
    }
    if (!payload || payload.audiovisual_analysis !== 'not_performed' || !payload.metadata) {
      return { ok: false, error: 'malformed' };
    }
    return {
      ok: true,
      context: {
        contextId: payload.context_id ?? null,
        videoId: payload.video_id ?? null,
        metadata: allowedMetadata(payload.metadata),
      },
    };
  } finally {
    clearTimeout(timer);
  }
}
