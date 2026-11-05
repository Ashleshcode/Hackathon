// @vitest-environment jsdom
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { describeTab, extractPage, youtubeVideoId } from './pageExtractor.js';

const at = (url) => new URL(url);

describe('X', () => {
  it('does not read post text, account, or media from an X page', () => {
    document.body.innerHTML = `
      <article data-testid="tweet">
        <div data-testid="tweetText">Target post</div>
        <div data-testid="tweetPhoto"><img src="https://pbs.example.invalid/a.jpg"></div>
      </article>`;
    const page = describeTab(at('https://x.com/demo_b/status/2'));
    expect(page).toMatchObject({
      platform: 'x',
      integration: 'pending_x_api',
      content_type: 'none',
      post_text: null,
      account: null,
      timestamp: null,
      media: [],
      video_id: null,
    });
    expect(extractPage(at('https://x.com/demo_b/status/2'))).toEqual(page);
  });

  it('treats timelines the same as posts: no page content', () => {
    const page = describeTab(at('https://x.com/home'));
    expect(page.platform).toBe('x');
    expect(page.content_type).toBe('none');
    expect(page.post_text).toBeNull();
  });
});

describe('YouTube', () => {
  it('keeps only the video id from a watch, short, embed, or youtu.be URL', () => {
    expect(youtubeVideoId(at('https://www.youtube.com/watch?v=abcdefghijk'))).toBe('abcdefghijk');
    expect(youtubeVideoId(at('https://youtube.com/shorts/abcdefghijk'))).toBe('abcdefghijk');
    expect(youtubeVideoId(at('https://www.youtube.com/embed/abcdefghijk'))).toBe('abcdefghijk');
    expect(youtubeVideoId(at('https://youtu.be/abcdefghijk'))).toBe('abcdefghijk');
    const page = describeTab(at('https://www.youtube.com/watch?v=abcdefghijk'));
    expect(page).toMatchObject({
      platform: 'youtube',
      integration: 'pending_youtube_metadata',
      video_id: 'abcdefghijk',
      content_type: 'none',
      post_text: null,
      media: [],
    });
  });

  it('does not read the title, channel, or video element', () => {
    document.head.innerHTML = '<meta property="og:title" content="Demo title"><meta property="og:image" content="https://i.ytimg.example/a.jpg">';
    document.body.innerHTML = '<ytd-watch-metadata><h1>Demo title</h1></ytd-watch-metadata><video src="https://example.invalid/video.mp4"></video>';
    const page = describeTab(at('https://www.youtube.com/watch?v=abcdefghijk'));
    expect(page.post_text).toBeNull();
    expect(page.account).toBeNull();
    expect(page.media).toEqual([]);
  });

  it('ignores the home page, a channel, and a playlist', () => {
    for (const url of [
      'https://www.youtube.com/',
      'https://www.youtube.com/channel/UCaaaaaaaaaaaa',
      'https://www.youtube.com/playlist?list=PLaaaaaaaaaaaa',
    ]) {
      expect(describeTab(at(url)).platform).toBe('unknown');
      expect(youtubeVideoId(at(url))).toBeNull();
    }
  });
});

describe('Instagram', () => {
  it('does not read a post even when metadata is present', () => {
    document.head.innerHTML =
      '<meta property="og:url" content="https://www.instagram.com/p/ABC/"><meta property="og:image" content="https://cdn.example.invalid/i.jpg"><meta property="og:description" content="Caption">';
    const page = describeTab(at('https://www.instagram.com/p/ABC/'));
    expect(page).toMatchObject({
      platform: 'unsupported',
      integration: 'instagram_removed',
      content_type: 'none',
      post_text: null,
      media: [],
    });
  });
});

describe('other pages', () => {
  it('reads nothing from unsupported sites', () => {
    document.body.innerHTML = '<article><p>Lookalike</p></article>';
    expect(describeTab(at('https://example.invalid/x.com/demo/status/2'))).toMatchObject({
      platform: 'unknown',
      integration: 'unsupported',
      content_type: 'none',
      post_text: null,
      media: [],
    });
  });
});

describe('manifest', () => {
  it('allows only the tab-capture permissions and has no content script', () => {
    const manifest = JSON.parse(readFileSync(resolve(__dirname, '../public/manifest.json'), 'utf8'));
    expect(manifest.manifest_version).toBe(3);
    expect(manifest.permissions.sort()).toEqual(['activeTab', 'offscreen', 'storage', 'tabCapture']);
    expect(manifest.host_permissions).toEqual(['http://localhost:8000/*']);
    expect(manifest.content_scripts).toBeUndefined();
    expect(manifest.background).toEqual({ service_worker: 'background.js', type: 'module' });
    expect(manifest.permissions).not.toContain('scripting');
    expect(manifest.permissions).not.toContain('history');
    expect(manifest.permissions).not.toContain('cookies');
    expect(manifest.permissions).not.toContain('debugger');
  });
});
