/* global chrome */
import { API_URL } from './config.js';
import { recordTabStream, tabCaptureConstraints, uploadTabVideo } from './tabCapture.js';

const VIDEO_TIMEOUT_MS = 120000;

chrome.runtime.sendMessage({ type: 'OFFSCREEN_READY' }).catch(() => {});
let stopRequested = false;
let activeToken = null;

function notify(type, payload) {
  return chrome.runtime.sendMessage({ target: 'background', type, token: activeToken, ...payload }).catch(() => {});
}

async function discardStream(stream) {
  stream?.getTracks?.().forEach((track) => track.stop());
}

chrome.runtime.onMessage.addListener((message) => {
  if (message?.target !== 'offscreen') return undefined;
  if (message.type === 'STOP_RECORDING') {
    stopRequested = true;
    return undefined;
  }
  if (message.type === 'START_RECORDING') {
    stopRequested = false;
    activeToken = message.token;
    capture(message.streamId);
  }
  return undefined;
});

async function capture(streamId) {
  let stream = null;
  try {
    stream = await navigator.mediaDevices.getUserMedia(tabCaptureConstraints(streamId));
    const recorded = await recordTabStream(stream, {
      MediaRecorder: globalThis.MediaRecorder,
      isTypeSupported: (type) => globalThis.MediaRecorder?.isTypeSupported(type) === true,
      shouldStop: () => stopRequested,
      onTick: (secondsLeft) => notify('CAPTURE_TICK', { secondsLeft }),
    });
    stream = null;
    if (!recorded.ok) {
      await notify('CAPTURE_FAILED', { error: recorded.error });
      return;
    }
    if (stopRequested) {
      recorded.blob = null;
      await notify('CAPTURE_FAILED', { error: 'cancelled' });
      return;
    }
    const uploaded = await uploadTabVideo(recorded.blob, {
      fetchImpl: fetch,
      apiUrl: API_URL,
      timeoutMs: VIDEO_TIMEOUT_MS,
      onPhase: (phase) => notify('CAPTURE_PHASE', { phase }),
    });
    recorded.blob = null;
    if (stopRequested) {
      await notify('CAPTURE_FAILED', { error: 'cancelled' });
      return;
    }
    if (uploaded.ok) await notify('CAPTURE_RESULT', { report: uploaded.report });
    else await notify('CAPTURE_FAILED', { error: uploaded.error, report: uploaded.report ?? null });
  } catch {
    await discardStream(stream);
    await notify('CAPTURE_FAILED', { error: 'stream_failed' });
  }
}
