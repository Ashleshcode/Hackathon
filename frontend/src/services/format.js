export const SIGNAL_LABELS = {
  same_media_hash: 'Same media hash',
  similar_caption: 'Similar caption',
  close_posting_time: 'Close posting time',
  shared_url: 'Shared URL',
};

export function signalLabel(type) {
  return SIGNAL_LABELS[type] ?? type;
}

// Scores are raw model output, so a missing score must never display as 0.
export function formatScore(score) {
  return typeof score === 'number' ? score.toFixed(2) : 'No score';
}

export function formatSeconds(seconds) {
  if (typeof seconds !== 'number') return 'Unknown';
  const minutes = Math.floor(seconds / 60);
  const remainder = (seconds - minutes * 60).toFixed(1).padStart(4, '0');
  return `${minutes}:${remainder}`;
}

export function formatTimestamp(value) {
  // new Date(null) is 1970, so a missing time has to be caught first.
  if (value === null || value === undefined) return 'Not available';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value ?? 'Unknown');
  return `${date.toISOString().slice(0, 16).replace('T', ' ')} UTC`;
}

// Imported URLs are untrusted, so only http(s) links are made clickable.
export function safeUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : null;
  } catch {
    return null;
  }
}
