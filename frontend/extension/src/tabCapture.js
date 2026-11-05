// Pure helpers for a user-started tab recording. No browser APIs live here.

export const RECORD_MS = 8000;
export const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;
export const VIDEO_BITS_PER_SECOND = 2_500_000;
export const MIME_CANDIDATES = ['video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm'];

export const ACTIVE_PHASES = ['preparing', 'recording', 'uploading', 'analysing'];

export function isActivePhase(phase) {
  return ACTIVE_PHASES.includes(phase);
}

export function selectMimeType(isTypeSupported) {
  if (typeof isTypeSupported !== 'function') return { ok: false, error: 'unsupported_mime' };
  const mimeType = MIME_CANDIDATES.find((candidate) => isTypeSupported(candidate));
  if (!mimeType) return { ok: false, error: 'unsupported_mime' };
  return { ok: true, mimeType };
}

export function tabCaptureConstraints(streamId) {
  return {
    audio: false,
    video: {
      mandatory: {
        chromeMediaSource: 'tab',
        chromeMediaSourceId: streamId,
        maxWidth: 1280,
        maxHeight: 720,
        maxFrameRate: 15,
      },
    },
  };
}

export function stopStream(stream) {
  const tracks = stream?.getTracks?.() ?? [];
  tracks.forEach((track) => track.stop());
  return tracks.length;
}

export function validateRecording(blob) {
  if (!blob || typeof blob.size !== 'number' || blob.size <= 0) return { ok: false, error: 'empty_recording' };
  if (blob.size > MAX_UPLOAD_BYTES) return { ok: false, error: 'recording_too_large' };
  if (typeof blob.type !== 'string' || !blob.type.startsWith('video/')) return { ok: false, error: 'invalid_recording' };
  return { ok: true };
}

export function buildVideoForm(blob) {
  const form = new FormData();
  form.append('file', blob, 'tab-capture.webm');
  return form;
}

export function badgeText(phase, secondsLeft) {
  if (phase === 'preparing') return '...';
  if (phase === 'recording') return String(secondsLeft ?? '');
  if (phase === 'uploading') return 'UP';
  if (phase === 'analysing') return 'AI';
  return '';
}

function finiteScore(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

export function interpretVideoReport(report) {
  if (!report || typeof report !== 'object' || Array.isArray(report)) return null;
  const result = report.result && typeof report.result === 'object' && !Array.isArray(report.result) ? report.result : null;
  const fakeScore = finiteScore(result?.fake_score);
  let outcome = 'failed';
  if (report.status === 'completed' && result?.status === 'no_face') outcome = 'no_face';
  else if (report.status === 'completed' && result?.status === 'indeterminate') outcome = 'uncertain';
  else if (report.status === 'completed' && result?.status === 'scored') {
    const prediction = result.prediction;
    if (prediction === 'fake' && fakeScore === 0.5) outcome = 'uncertain';
    else if (prediction === 'fake' || prediction === 'real' || prediction === 'uncertain') outcome = prediction;
    else outcome = 'uncertain';
  }
  const warnings = Array.isArray(result?.warnings) ? result.warnings.filter((item) => typeof item === 'string') : [];
  return {
    reportId: typeof report.report_id === 'string' ? report.report_id : null,
    jobStatus: typeof report.status === 'string' ? report.status : null,
    mediaType: report.media_type ?? result?.media_type ?? null,
    detectorStatus: result?.status ?? null,
    prediction: result?.prediction ?? null,
    fakeScore: outcome === 'no_face' ? null : fakeScore,
    scoreSemantics: result?.score_semantics ?? null,
    warnings,
    framesSampled: result?.frames_sampled ?? null,
    framesScored: result?.frames_scored ?? null,
    framesWithFaces: result?.frames_with_faces ?? null,
    aggregationMethod: result?.aggregation_method ?? null,
    aggregatePrediction: result?.aggregate_prediction ?? null,
    aggregateFakeScore: finiteScore(result?.aggregate_fake_score),
    outcome,
  };
}

export const OUTCOME_LABELS = {
  fake: 'Fake',
  real: 'Real',
  uncertain: 'Uncertain',
  no_face: 'No face',
  failed: 'Failed',
};

async function readBody(response) {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

function failedReport(payload) {
  const detail = payload?.detail;
  if (detail && typeof detail === 'object' && !Array.isArray(detail) && typeof detail.report_id === 'string') return detail;
  if (payload && typeof payload.report_id === 'string' && payload.status && payload.status !== 'completed') return payload;
  return null;
}

export async function uploadTabVideo(blob, { fetchImpl, apiUrl, timeoutMs, onPhase }) {
  const validation = validateRecording(blob);
  if (!validation.ok) return validation;
  const form = buildVideoForm(blob);
  if (![...form.keys()].every((key) => key === 'file')) return { ok: false, error: 'invalid_recording' };
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    onPhase?.('uploading');
    let response;
    try {
      onPhase?.('analysing');
      response = await fetchImpl(`${apiUrl}/api/analyze/video`, { method: 'POST', body: form, signal: controller.signal });
    } catch (error) {
      if (error?.name === 'AbortError') return { ok: false, error: 'timeout' };
      return { ok: false, error: 'unavailable' };
    }
    const payload = await readBody(response);
    if (response.ok && payload?.status === 'completed') return { ok: true, report: payload };
    const report = failedReport(payload);
    if (report) return { ok: false, error: 'analysis_failed', report, status: response.status };
    return { ok: false, error: 'server', status: response.status };
  } finally {
    clearTimeout(timer);
  }
}

export async function fetchStoredReport(reportId, { fetchImpl, apiUrl, timeoutMs }) {
  if (typeof reportId !== 'string' || !/^[A-Za-z0-9_-]+$/.test(reportId)) return { ok: false, error: 'not_found' };
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    let response;
    try {
      response = await fetchImpl(`${apiUrl}/api/reports/${encodeURIComponent(reportId)}`, { signal: controller.signal });
    } catch (error) {
      if (error?.name === 'AbortError') return { ok: false, error: 'timeout' };
      return { ok: false, error: 'unavailable' };
    }
    const payload = await readBody(response);
    if (response.status === 200 && payload?.status === 'completed') return { ok: true, report: payload };
    const report = failedReport(payload);
    if (response.status === 409 && report) return { ok: false, error: 'analysis_failed', report };
    if (response.status === 404) return { ok: false, error: 'not_found' };
    return { ok: false, error: 'server', status: response.status };
  } finally {
    clearTimeout(timer);
  }
}

export function delay(ms, signal) {
  return new Promise((resolve) => {
    const timer = setTimeout(finish, ms);
    function finish() {
      clearTimeout(timer);
      signal?.removeEventListener('abort', finish);
      resolve();
    }
    signal?.addEventListener('abort', finish, { once: true });
  });
}

export async function recordTabStream(stream, { MediaRecorder, isTypeSupported, durationMs = RECORD_MS, onTick, shouldStop, videoBitsPerSecond = VIDEO_BITS_PER_SECOND }) {
  const audioTracks = stream?.getAudioTracks?.() ?? [];
  audioTracks.forEach((track) => track.stop());
  if (!stream?.getVideoTracks?.().length) {
    stopStream(stream);
    return { ok: false, error: 'stream_failed' };
  }
  const selected = selectMimeType(isTypeSupported);
  if (!selected.ok) {
    stopStream(stream);
    return selected;
  }
  let recorder;
  try {
    recorder = new MediaRecorder(stream, { mimeType: selected.mimeType, videoBitsPerSecond });
  } catch {
    stopStream(stream);
    return { ok: false, error: 'unsupported_mime' };
  }
  const chunks = [];
  recorder.ondataavailable = (event) => {
    if (event.data?.size > 0) chunks.push(event.data);
  };
  const stopped = new Promise((resolve) => {
    recorder.onstop = () => resolve();
    recorder.onerror = () => resolve();
  });
  recorder.start(1000);
  const started = Date.now();
  let cancelled = false;
  try {
    while (Date.now() - started < durationMs) {
      if (shouldStop?.()) {
        cancelled = true;
        break;
      }
      onTick?.(Math.max(1, Math.ceil((durationMs - (Date.now() - started)) / 1000)));
      await delay(200);
    }
  } finally {
    if (recorder.state !== 'inactive') recorder.stop();
    await stopped;
    stopStream(stream);
  }
  if (cancelled) return { ok: false, error: 'cancelled' };
  const recordedType = typeof recorder.mimeType === 'string' && recorder.mimeType.startsWith('video/') ? recorder.mimeType : selected.mimeType;
  const blob = new Blob(chunks, { type: recordedType });
  const validation = validateRecording(blob);
  if (!validation.ok) return validation;
  return { ok: true, blob, mimeType: recordedType };
}

export function videoFailureMessage(report) {
  const code = report?.result?.error_code;
  const status = report?.result?.status;
  if (code === 'unreadable_video' || code === 'invalid_video_metadata' || status === 'invalid_media') {
    return 'The recorded tab video could not be decoded, so DeepGuard did not score it.';
  }
  return null;
}
