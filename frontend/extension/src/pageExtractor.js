// Classifies the current tab from its URL only.
// It does not read the page, inject a script, or collect media.
// X text, X media, and Instagram pages are intentionally ignored.

const VIDEO_ID = /^[\w-]{11}$/;

export function youtubeVideoId(href) {
  let url;
  try {
    url = href instanceof URL ? href : new URL(href);
  } catch {
    return null;
  }
  const host = url.hostname.replace(/^(www|m|mobile)\./, '');
  if (host === 'youtu.be') {
    const id = url.pathname.split('/').filter(Boolean)[0] ?? '';
    return VIDEO_ID.test(id) ? id : null;
  }
  if (host !== 'youtube.com') return null;
  if (url.pathname === '/watch') {
    const id = url.searchParams.get('v') ?? '';
    return VIDEO_ID.test(id) ? id : null;
  }
  const embedded = url.pathname.match(/^\/(?:embed|shorts)\/([\w-]{11})/);
  return embedded ? embedded[1] : null;
}

export function describeTab(href) {
  let url;
  try {
    url = href instanceof URL ? href : new URL(href);
  } catch {
    return null;
  }
  const host = url.hostname.replace(/^(www|m|mobile)\./, '');
  const base = {
    url: url.href,
    post_text: null,
    account: null,
    timestamp: null,
    media: [],
    video_id: null,
  };
  if (host === 'x.com' || host === 'twitter.com') {
    return { ...base, platform: 'x', content_type: 'none', integration: 'pending_x_api' };
  }
  if (host === 'instagram.com') {
    return { ...base, platform: 'unsupported', content_type: 'none', integration: 'instagram_removed' };
  }
  const videoId = youtubeVideoId(url);
  if (videoId) {
    return {
      ...base,
      platform: 'youtube',
      content_type: 'none',
      video_id: videoId,
      integration: 'pending_youtube_metadata',
    };
  }
  return { ...base, platform: 'unknown', content_type: 'none', integration: 'unsupported' };
}

// Kept so a leftover injection cannot scrape the DOM. It ignores document.
export function extractPage(loc = { href: '' }) {
  return describeTab(loc.href);
}
