/* global chrome */
import { describeTab } from './pageExtractor.js';

const MODE_KEY = 'veritas_mode';
const ACTIONS_KEY = 'veritas_actions';

// Reads the active tab URL only after the analyst opens the popup.
// It does not inject a script, read the page, or write the URL to storage.
export async function readCurrentPage() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.url) return null;
  return describeTab(tab.url);
}

export async function getSavedMode() {
  const stored = await chrome.storage.local.get(MODE_KEY);
  return stored[MODE_KEY] === 'live' ? 'live' : 'demo';
}

export function saveMode(mode) {
  return chrome.storage.local.set({ [MODE_KEY]: mode });
}

export async function getActions() {
  const stored = await chrome.storage.local.get(ACTIONS_KEY);
  return stored[ACTIONS_KEY] ?? {};
}

// Prototype actions: stored in this browser only and never sent to any platform.
export async function toggleAction(action, url, details) {
  const all = await getActions();
  const items = all[action] ?? [];
  const exists = items.some((item) => item.url === url);
  const next = exists ? items.filter((item) => item.url !== url) : [...items, { url, ...details, saved_at: new Date().toISOString() }];
  await chrome.storage.local.set({ [ACTIONS_KEY]: { ...all, [action]: next } });
  return !exists;
}

export function openTab(url) {
  return chrome.tabs.create({ url });
}
