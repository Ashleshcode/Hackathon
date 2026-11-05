/* global chrome */
import { createCaptureController } from './captureController.js';

const SESSION_KEY = 'veritas_tab_capture';

async function persistState(state) {
  const stored = {
    phase: state.phase,
    secondsLeft: state.secondsLeft,
    error: state.error,
    report: state.report ?? null,
    tabId: state.tabId ?? null,
    token: controller.currentToken(),
  };
  await chrome.storage.session.set({ [SESSION_KEY]: stored });
  chrome.runtime.sendMessage({ target: 'popup', type: 'CAPTURE_STATE', state: stored }).catch(() => {});
}

const hydrated = chrome.storage.session.get(SESSION_KEY).then(async (stored) => {
  const saved = stored?.[SESSION_KEY];
  if (!saved) return;
  controller.restore(saved);
  if (saved.phase === 'preparing' || saved.phase === 'recording' || saved.phase === 'uploading' || saved.phase === 'analysing') {
    const contexts = await chrome.runtime.getContexts({ contextTypes: ['OFFSCREEN_DOCUMENT'] });
    if (contexts.length === 0) await controller.onFailure('stream_failed', saved.report ?? null, controller.currentToken());
  }
});

let controller;
let markOffscreenReady = () => {};

controller = createCaptureController({
  getActiveTab: async () => {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    return tab ?? null;
  },
  ensureOffscreen: async () => {
    const contexts = await chrome.runtime.getContexts({ contextTypes: ['OFFSCREEN_DOCUMENT'] });
    if (contexts.length > 0) return;
    const ready = new Promise((resolve) => {
      markOffscreenReady = resolve;
    });
    await chrome.offscreen.createDocument({
      url: 'offscreen.html',
      reasons: ['USER_MEDIA'],
      justification: 'Record the active tab after the user clicks Analyse this video.',
    });
    await Promise.race([ready, new Promise((resolve) => setTimeout(resolve, 2000))]);
  },
  getStreamId: (tabId) => chrome.tabCapture.getMediaStreamId({ targetTabId: tabId }),
  startRecording: (payload) => chrome.runtime.sendMessage({ target: 'offscreen', type: 'START_RECORDING', ...payload, token: controller.currentToken() }),
  stopRecording: () => chrome.runtime.sendMessage({ target: 'offscreen', type: 'STOP_RECORDING' }).catch(() => {}),
  releaseOffscreen: async () => {
    const contexts = await chrome.runtime.getContexts({ contextTypes: ['OFFSCREEN_DOCUMENT'] });
    if (contexts.length > 0) await chrome.offscreen.closeDocument();
  },
  persistState,
  setBadge: async (text) => {
    await chrome.action.setBadgeBackgroundColor({ color: '#9a3412' });
    await chrome.action.setBadgeText({ text });
  },
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === 'OFFSCREEN_READY') {
    markOffscreenReady();
    return undefined;
  }
  if (message?.target === 'offscreen') return undefined;
  if (message?.type === 'GET_CAPTURE_STATE') {
    hydrated.then(() => sendResponse(controller.getState()));
    return true;
  }
  if (message?.type === 'START_CAPTURE') {
    hydrated.then(() => controller.start()).then(sendResponse);
    return true;
  }
  if (message?.type === 'CANCEL_CAPTURE') {
    hydrated.then(() => controller.cancel()).then(sendResponse);
    return true;
  }
  if (message?.type === 'CLEAR_CAPTURE') {
    hydrated.then(() => controller.clear()).then(sendResponse);
    return true;
  }
  if (message?.type === 'CAPTURE_TICK') {
    hydrated.then(() => controller.onTick(message.secondsLeft, message.token)).then(() => sendResponse({ ok: true }));
    return true;
  }
  if (message?.type === 'CAPTURE_PHASE') {
    hydrated.then(() => controller.onPhase(message.phase, message.token)).then(() => sendResponse({ ok: true }));
    return true;
  }
  if (message?.type === 'CAPTURE_RESULT') {
    hydrated.then(() => controller.onResult(message.report, message.token)).then(() => sendResponse({ ok: true }));
    return true;
  }
  if (message?.type === 'CAPTURE_FAILED') {
    hydrated.then(() => controller.onFailure(message.error, message.report, message.token)).then(() => sendResponse({ ok: true }));
    return true;
  }
  return undefined;
});

chrome.tabs.onRemoved.addListener((tabId) => {
  controller.onTabClosed(tabId);
});
