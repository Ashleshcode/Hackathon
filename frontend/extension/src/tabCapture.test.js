import { describe, expect, it } from 'vitest';
import { createCaptureController } from './captureController.js';
import {
  fetchStoredReport,
  interpretVideoReport,
  recordTabStream,
  selectMimeType,
  tabCaptureConstraints,
  uploadTabVideo,
  validateRecording,
  videoFailureMessage,
} from './tabCapture.js';

const json = (body, status = 200) => new Response(JSON.stringify(body), { status });

function stream({ video = true, audio = false } = {}) {
  const stopped = [];
  const track = (kind) => ({ kind, stop: () => stopped.push(kind) });
  const videoTracks = video ? [track('video')] : [];
  const audioTracks = audio ? [track('audio')] : [];
  return { getVideoTracks: () => videoTracks, getAudioTracks: () => audioTracks, getTracks: () => [...videoTracks, ...audioTracks], stopped };
}

function recorderFactory(chunks) {
  return class FakeRecorder {
    constructor(_stream, options) {
      this.options = options;
      this.state = 'inactive';
    }

    start() {
      this.state = 'recording';
    }

    stop() {
      chunks.forEach((chunk) => this.ondataavailable?.({ data: chunk }));
      this.state = 'inactive';
      this.onstop?.();
    }
  };
}

const completed = {
  report_id: 'rpt_1',
  job_id: 'rpt_1',
  status: 'completed',
  media_type: 'video',
  result: {
    status: 'scored',
    media_type: 'video',
    prediction: 'uncertain',
    fake_score: 0.5,
    score_semantics: 'raw_model_score_not_calibrated_probability',
    warnings: ['fake_score is a raw sigmoid output, not a calibrated probability.'],
    frames_sampled: 4,
    frames_scored: 4,
    aggregation_method: 'median of scored face frames',
    aggregate_prediction: 'uncertain',
    aggregate_fake_score: 0.5,
  },
};

describe('tab capture constraints and recording', () => {
  it('requests a video-only tab stream', () => {
    const constraints = tabCaptureConstraints('stream-1');
    expect(constraints.audio).toBe(false);
    expect(constraints.video.mandatory.chromeMediaSource).toBe('tab');
    expect(constraints.video.mandatory.chromeMediaSourceId).toBe('stream-1');
    expect(constraints.video.mandatory.audio).toBeUndefined();
  });

  it('fails when no WebM recorder type is supported', async () => {
    const media = stream();
    const result = await recordTabStream(media, { MediaRecorder: class {}, isTypeSupported: () => false, durationMs: 10 });
    expect(result).toEqual({ ok: false, error: 'unsupported_mime' });
    expect(media.stopped).toEqual(['video']);
  });

  it('fails when the stream cannot be acquired', async () => {
    const media = stream({ video: false });
    const result = await recordTabStream(media, { MediaRecorder: class {}, isTypeSupported: () => true });
    expect(result.error).toBe('stream_failed');
  });

  it('stops audio tracks and rejects an empty recording', async () => {
    const media = stream({ audio: true });
    const result = await recordTabStream(media, {
      MediaRecorder: recorderFactory([]),
      isTypeSupported: (type) => type === 'video/webm',
      durationMs: 10,
    });
    expect(result.error).toBe('empty_recording');
    expect(media.stopped).toContain('audio');
    expect(media.stopped).toContain('video');
  });

  it('keeps the final chunk and the recorder MIME type', async () => {
    const media = stream();
    const chunk = new Blob([new Uint8Array(24)], { type: 'video/webm' });
    class FinalChunkRecorder extends recorderFactory([chunk]) {
      mimeType = 'video/webm;codecs=vp8';
    }
    const result = await recordTabStream(media, {
      MediaRecorder: FinalChunkRecorder,
      isTypeSupported: () => true,
      durationMs: 10,
    });
    expect(result.ok).toBe(true);
    expect(result.mimeType).toBe('video/webm;codecs=vp8');
    expect(result.blob.type).toBe('video/webm;codecs=vp8');
    expect(result.blob.size).toBeGreaterThan(0);
    const form = new FormData();
    form.append('file', result.blob, 'tab-capture.webm');
    expect([...form.keys()]).toEqual(['file']);
  });

  it('returns a video blob and stops the stream when recording finishes', async () => {
    const media = stream();
    const chunk = new Blob([new Uint8Array(16)], { type: 'video/webm' });
    const result = await recordTabStream(media, {
      MediaRecorder: recorderFactory([chunk]),
      isTypeSupported: () => true,
      durationMs: 10,
    });
    expect(result.ok).toBe(true);
    expect(result.blob.size).toBeGreaterThan(0);
    expect(result.blob.type).toContain('video/webm');
    expect(media.stopped).toEqual(['video']);
  });

  it('cancels before producing an upload', async () => {
    const media = stream();
    const result = await recordTabStream(media, {
      MediaRecorder: recorderFactory([new Blob([new Uint8Array(8)], { type: 'video/webm' })]),
      isTypeSupported: () => true,
      durationMs: 5000,
      shouldStop: () => true,
    });
    expect(result.error).toBe('cancelled');
    expect(media.stopped).toEqual(['video']);
  });

  it('rejects an empty or oversized blob before upload', () => {
    expect(validateRecording(new Blob([], { type: 'video/webm' })).error).toBe('empty_recording');
    expect(validateRecording(new Blob([new Uint8Array(8)], { type: 'text/plain' })).error).toBe('invalid_recording');
    expect(selectMimeType(() => false).error).toBe('unsupported_mime');
  });
});

describe('video upload and stored reports', () => {
  const blob = new Blob([new Uint8Array(32)], { type: 'video/webm' });

  it('posts one file field and keeps an uncertain 0.5 result', async () => {
    const calls = [];
    const fetchImpl = async (url, options) => {
      calls.push({ url, options });
      return json(completed);
    };
    const phases = [];
    const result = await uploadTabVideo(blob, { fetchImpl, apiUrl: 'http://localhost:8000', timeoutMs: 1000, onPhase: (phase) => phases.push(phase) });
    expect(result.ok).toBe(true);
    expect(calls[0].url).toBe('http://localhost:8000/api/analyze/video');
    expect(calls[0].options.method).toBe('POST');
    expect([...calls[0].options.body.keys()]).toEqual(['file']);
    expect(phases).toEqual(['uploading', 'analysing']);
    const view = interpretVideoReport(result.report);
    expect(view.outcome).toBe('uncertain');
    expect(view.fakeScore).toBe(0.5);
    expect(view.prediction).toBe('uncertain');
  });

  it('shows a failed job from a 422 body without calling it a success', async () => {
    const failed = { ...completed, status: 'failed', result: { status: 'inference_error', prediction: null, fake_score: null, warnings: [] } };
    const fetchImpl = async () => json({ detail: failed }, 422);
    const result = await uploadTabVideo(blob, { fetchImpl, apiUrl: 'http://localhost:8000', timeoutMs: 1000 });
    expect(result.ok).toBe(false);
    expect(result.error).toBe('analysis_failed');
    expect(interpretVideoReport(result.report).outcome).toBe('failed');
  });

  it('reports a server error and a network failure separately', async () => {
    const server = await uploadTabVideo(blob, { fetchImpl: async () => json({ detail: 'no' }, 500), apiUrl: 'http://localhost:8000', timeoutMs: 1000 });
    expect(server).toMatchObject({ ok: false, error: 'server', status: 500 });
    const offline = await uploadTabVideo(blob, {
      fetchImpl: async () => {
        throw new TypeError('Failed to fetch');
      },
      apiUrl: 'http://localhost:8000',
      timeoutMs: 1000,
    });
    expect(offline.error).toBe('unavailable');
  });

  it('does not upload an empty recording', async () => {
    let called = false;
    const result = await uploadTabVideo(new Blob([], { type: 'video/webm' }), {
      fetchImpl: async () => {
        called = true;
        return json(completed);
      },
      apiUrl: 'http://localhost:8000',
      timeoutMs: 1000,
    });
    expect(result.error).toBe('empty_recording');
    expect(called).toBe(false);
  });

  it('reads a stored report and keeps a failed report unsuccessful', async () => {
    const ok = await fetchStoredReport('rpt_1', { fetchImpl: async () => json(completed), apiUrl: 'http://localhost:8000', timeoutMs: 1000 });
    expect(ok.ok).toBe(true);
    const failed = await fetchStoredReport('rpt_2', {
      fetchImpl: async () => json({ detail: { ...completed, status: 'failed', result: null } }, 409),
      apiUrl: 'http://localhost:8000',
      timeoutMs: 1000,
    });
    expect(failed.ok).toBe(false);
    expect(failed.error).toBe('analysis_failed');
  });
});

describe('video report labels', () => {
  it('keeps no face separate from fake and real', () => {
    const view = interpretVideoReport({
      report_id: 'rpt_face',
      status: 'completed',
      media_type: 'video',
      result: { status: 'no_face', prediction: null, fake_score: null, score_semantics: 'raw_model_score_not_calibrated_probability', warnings: [] },
    });
    expect(view.outcome).toBe('no_face');
    expect(view.fakeScore).toBeNull();
    expect(view.prediction).toBeNull();
  });

  it('explains an undecoded tab video without treating it as a verdict', () => {
    const report = {
      status: 'failed',
      media_type: 'video',
      result: { status: 'invalid_media', prediction: null, fake_score: null, error_code: 'unreadable_video' },
    };
    expect(interpretVideoReport(report).outcome).toBe('failed');
    expect(interpretVideoReport(report).prediction).toBeNull();
    expect(videoFailureMessage(report)).toBe('The recorded tab video could not be decoded, so DeepGuard did not score it.');
  });

  it('does not treat a raw score of 0.5 as fake', () => {
    const view = interpretVideoReport({
      status: 'completed',
      result: { status: 'scored', prediction: 'fake', fake_score: 0.5 },
    });
    expect(view.outcome).toBe('uncertain');
  });
});

describe('capture controller', () => {
  function harness(overrides = {}) {
    const calls = [];
    const controller = createCaptureController({
      getActiveTab: async () => ({ id: 4 }),
      ensureOffscreen: async () => calls.push('offscreen'),
      getStreamId: async (tabId) => {
        calls.push(`stream:${tabId}`);
        return 'sid';
      },
      startRecording: async () => calls.push('record'),
      stopRecording: async () => calls.push('stop'),
      releaseOffscreen: async () => calls.push('release'),
      persistState: async () => {},
      setBadge: async () => {},
      ...overrides,
    });
    return { controller, calls };
  }

  it('creates the offscreen document before requesting the stream id', async () => {
    const { controller, calls } = harness();
    const result = await controller.start();
    expect(result.ok).toBe(true);
    expect(calls).toEqual(['offscreen', 'stream:4', 'record']);
  });

  it('rejects a second start while a capture is active', async () => {
    let release;
    const { controller } = harness({ getActiveTab: () => new Promise((resolve) => { release = resolve; }) });
    const first = controller.start();
    for (let step = 0; step < 5; step += 1) await Promise.resolve();
    const second = await controller.start();
    expect(second.error).toBe('already_active');
    expect(typeof release).toBe('function');
    release({ id: 4 });
    await first;
    expect(controller.getState().phase).toBe('recording');
  });

  it('cleans up when the stream id cannot be obtained', async () => {
    const { controller, calls } = harness({
      getStreamId: async () => {
        throw new Error('denied');
      },
    });
    const result = await controller.start();
    expect(result.error).toBe('stream_failed');
    expect(calls).toContain('stop');
    expect(calls).toContain('release');
    expect(controller.getState().phase).toBe('failed');
  });

  it('cancels an active capture and ignores a late success', async () => {
    const { controller, calls } = harness();
    await controller.start();
    const token = controller.currentToken();
    await controller.cancel();
    await controller.onResult(completed, token);
    expect(calls).toContain('stop');
    expect(controller.getState().phase).toBe('cancelled');
    expect(controller.getState().report).toBeNull();
  });

  it('accepts a finished report after the capture token is restored', async () => {
    const { controller } = harness();
    controller.restore({ phase: 'recording', secondsLeft: 2, tabId: 4, token: 3, report: null, error: null });
    await controller.onResult(completed, 3);
    expect(controller.getState().phase).toBe('completed');
    expect(controller.getState().report.report_id).toBe('rpt_1');
  });

  it('stops capture when the recorded tab closes', async () => {
    const { controller, calls } = harness();
    await controller.start();
    await controller.onTabClosed(9);
    expect(calls).not.toContain('stop');
    await controller.onTabClosed(4);
    expect(controller.getState().phase).toBe('cancelled');
  });
});
