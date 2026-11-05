import { useEffect, useState } from 'react';
import { API_URL } from './config.js';
import { fetchStoredReport, interpretVideoReport, isActivePhase, OUTCOME_LABELS, videoFailureMessage } from './tabCapture.js';

const VIDEO_TIMEOUT_MS = 120000;

const PHASE_LABELS = {
  preparing: 'Preparing capture',
  recording: 'Recording',
  uploading: 'Uploading to Veritas',
  analysing: 'Analysing with DeepGuard',
  completed: 'Completed',
  failed: 'Failed',
  cancelled: 'Capture stopped',
};

const ERROR_TEXT = {
  already_active: 'A tab capture is already in progress.',
  no_tab: 'Veritas cannot see an active tab to record.',
  stream_failed: 'Chrome could not capture this tab. Protected or restricted playback cannot be recorded.',
  unsupported_mime: 'This browser cannot record a WebM video from the tab.',
  empty_recording: 'The recording was empty, so nothing was uploaded.',
  recording_too_large: 'The recording is larger than the 20 MB limit, so it was not uploaded.',
  invalid_recording: 'The recording was not a valid video, so nothing was uploaded.',
  unavailable: 'The Veritas API could not be reached. The recording was not marked as analysed.',
  timeout: 'The Veritas API took too long to respond.',
  server: 'The Veritas API rejected the recording.',
  cancelled: 'Capture stopped. The recording was discarded.',
  analysis_failed: 'DeepGuard did not complete a successful score for this recording.',
  not_found: 'That stored report was not found.',
};

function messageFor(code) {
  return ERROR_TEXT[code] ?? 'The tab capture could not be completed.';
}

function send(type) {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage({ type }, (reply) => resolve(reply));
  });
}

function ReportDetails({ report }) {
  const view = interpretVideoReport(report);
  if (!view) return <p className="muted small">The stored response could not be read.</p>;
  const showScore = view.outcome !== 'no_face' && view.outcome !== 'failed' && view.fakeScore !== null;
  return (
    <div className="capture-report">
      <strong className="result-title">{OUTCOME_LABELS[view.outcome] ?? 'Failed'}</strong>
      <dl className="page-summary">
        <div>
          <dt>Report ID</dt>
          <dd className="mono">{view.reportId ?? 'None'}</dd>
        </div>
        <div>
          <dt>Job status</dt>
          <dd>{view.jobStatus ?? 'Unknown'}</dd>
        </div>
        <div>
          <dt>Media type</dt>
          <dd>{view.mediaType ?? 'Unknown'}</dd>
        </div>
        <div>
          <dt>Detector status</dt>
          <dd>{view.detectorStatus ?? 'None'}</dd>
        </div>
        <div>
          <dt>Prediction</dt>
          <dd>{view.prediction ?? 'None'}</dd>
        </div>
        <div>
          <dt>Raw model score</dt>
          <dd>{showScore ? String(view.fakeScore) : 'None'}</dd>
        </div>
      </dl>
      {view.scoreSemantics && <p className="muted small">{view.scoreSemantics}</p>}
      {view.framesSampled !== null && (
        <p className="muted small">
          Frames sampled {view.framesSampled}, scored {view.framesScored ?? 'none'}. {view.aggregationMethod}
        </p>
      )}
      {view.warnings.map((warning) => (
        <p key={warning} className="muted small">
          {warning}
        </p>
      ))}
      <p className="muted small">
        {view.outcome === 'failed'
          ? 'DeepGuard did not produce a fake or real verdict for this recorded tab video.'
          : 'This is the stored detector result for the recorded tab video, not a confidence percentage.'}
      </p>
    </div>
  );
}

export default function TabCaptureCard() {
  const [state, setState] = useState({ phase: 'idle', secondsLeft: null, report: null, error: null });
  const [reloadError, setReloadError] = useState(null);
  const active = isActivePhase(state.phase);

  useEffect(() => {
    if (typeof chrome === 'undefined' || !chrome.runtime?.sendMessage) return undefined;
    send('GET_CAPTURE_STATE').then((next) => {
      if (next?.phase) setState(next);
    });
    const listener = (message) => {
      if (message?.target === 'popup' && message.type === 'CAPTURE_STATE' && message.state?.phase) setState(message.state);
    };
    chrome.runtime.onMessage.addListener(listener);
    return () => chrome.runtime.onMessage.removeListener(listener);
  }, []);

  const start = async () => {
    setReloadError(null);
    const reply = await send('START_CAPTURE');
    if (reply?.state) setState(reply.state);
    else if (reply?.error) setState((current) => ({ ...current, phase: 'failed', error: reply.error }));
  };

  const reload = async () => {
    setReloadError(null);
    const reportId = state.report?.report_id;
    const outcome = await fetchStoredReport(reportId, { fetchImpl: fetch, apiUrl: API_URL, timeoutMs: VIDEO_TIMEOUT_MS });
    if (outcome.ok) setState((current) => ({ ...current, phase: 'completed', report: outcome.report, error: null }));
    else {
      setReloadError(messageFor(outcome.error));
      if (outcome.report) setState((current) => ({ ...current, phase: 'failed', report: outcome.report, error: outcome.error }));
    }
  };

  return (
    <section className="popup-card capture-card">
      <span className="eyebrow">Visible tab</span>
      <p className="muted small">
        Veritas will capture approximately 8 seconds of the currently visible browser tab and send the recording to your configured Veritas backend for analysis.
      </p>
      <p className="muted small">Tab capture records the picture on the tab after this click. It does not record audio, read the page, or keep the recording.</p>
      {state.phase === 'idle' && (
        <button type="button" className="button button-primary popup-primary" onClick={start}>
          Analyse this video
        </button>
      )}
      {active && (
        <>
          <p className="result-title" role="status">
            {PHASE_LABELS[state.phase]}
            {state.phase === 'recording' ? ` · ${state.secondsLeft ?? 8}s` : ''}
          </p>
          <button type="button" className="button button-secondary" onClick={() => send('CANCEL_CAPTURE')}>
            Stop capture
          </button>
        </>
      )}
      {state.phase === 'completed' && state.report && (
        <>
          <p className="result-title">{PHASE_LABELS.completed}</p>
          <ReportDetails report={state.report} />
        </>
      )}
      {(state.phase === 'failed' || state.phase === 'cancelled') && (
        <p className="notice notice-error" role="alert">
          {videoFailureMessage(state.report) ?? messageFor(state.error)}
        </p>
      )}
      {state.phase === 'failed' && state.report && <ReportDetails report={state.report} />}
      {state.report?.report_id && !active && (
        <button type="button" className="button button-secondary" onClick={reload}>
          Reload stored report
        </button>
      )}
      {reloadError && <p className="muted small">{reloadError}</p>}
      {(state.phase === 'completed' || state.phase === 'failed' || state.phase === 'cancelled') && (
        <button
          type="button"
          className="link-button small"
          onClick={() => {
            setState({ phase: 'idle', secondsLeft: null, report: null, error: null });
            send('CLEAR_CAPTURE');
          }}
        >
          Dismiss
        </button>
      )}
    </section>
  );
}
