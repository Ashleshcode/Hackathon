// Coordinates one tab capture. Browser calls are injected so tests can fake them.

import { badgeText, isActivePhase } from './tabCapture.js';

const idle = { phase: 'idle', secondsLeft: null, report: null, error: null, tabId: null };

export function createCaptureController(deps) {
  let state = { ...idle };
  let operation = 0;

  const snapshot = () => ({ ...state, report: state.report });

  async function publish() {
    await deps.persistState?.(snapshot());
    await deps.setBadge?.(badgeText(state.phase, state.secondsLeft));
  }

  async function finish(next, token) {
    if (token !== operation) return snapshot();
    state = { ...idle, ...next };
    await deps.releaseOffscreen?.();
    await publish();
    return snapshot();
  }

  return {
    getState: snapshot,
    async start() {
      if (isActivePhase(state.phase)) return { ok: false, error: 'already_active', state: snapshot() };
      const token = ++operation;
      state = { phase: 'preparing', secondsLeft: 8, report: null, error: null, tabId: null };
      await publish();
      try {
        const tab = await deps.getActiveTab();
        if (token !== operation) return { ok: false, error: 'cancelled', state: snapshot() };
        if (!tab?.id) {
          await finish({ phase: 'failed', error: 'no_tab' }, token);
          return { ok: false, error: 'no_tab', state: snapshot() };
        }
        state = { ...state, tabId: tab.id };
        await deps.ensureOffscreen();
        if (token !== operation) return { ok: false, error: 'cancelled', state: snapshot() };
        const streamId = await deps.getStreamId(tab.id);
        if (token !== operation) return { ok: false, error: 'cancelled', state: snapshot() };
        await deps.startRecording({ streamId, tabId: tab.id });
        if (token !== operation) return { ok: false, error: 'cancelled', state: snapshot() };
        state = { ...state, phase: 'recording' };
        await publish();
        return { ok: true, state: snapshot() };
      } catch {
        await deps.stopRecording?.();
        await finish({ phase: 'failed', error: 'stream_failed' }, token);
        return { ok: false, error: 'stream_failed', state: snapshot() };
      }
    },
    async cancel() {
      if (!isActivePhase(state.phase)) return snapshot();
      const token = ++operation;
      await deps.stopRecording?.();
      return finish({ phase: 'cancelled', error: 'cancelled' }, token);
    },
    async onTick(secondsLeft, token) {
      if (token !== operation || state.phase !== 'recording') return snapshot();
      state = { ...state, secondsLeft };
      await publish();
      return snapshot();
    },
    async onPhase(phase, token) {
      if (token !== operation || !isActivePhase(state.phase)) return snapshot();
      state = { ...state, phase };
      await publish();
      return snapshot();
    },
    async onResult(report, token) {
      if (token !== operation) return snapshot();
      return finish({ phase: 'completed', report, error: null, tabId: state.tabId }, token);
    },
    async onFailure(error, report, token) {
      if (token !== operation) return snapshot();
      return finish({ phase: 'failed', error, report: report ?? null, tabId: state.tabId }, token);
    },
    async onTabClosed(tabId) {
      if (!isActivePhase(state.phase) || tabId !== state.tabId) return snapshot();
      return this.cancel();
    },
    async clear() {
      if (isActivePhase(state.phase)) return snapshot();
      state = { ...idle };
      await publish();
      return snapshot();
    },
    currentToken: () => operation,
    restore(saved) {
      if (!saved || typeof saved !== 'object') return snapshot();
      if (typeof saved.token === 'number') operation = saved.token;
      state = {
        phase: typeof saved.phase === 'string' ? saved.phase : 'idle',
        secondsLeft: saved.secondsLeft ?? null,
        report: saved.report ?? null,
        error: saved.error ?? null,
        tabId: saved.tabId ?? null,
      };
      return snapshot();
    },
  };
}
