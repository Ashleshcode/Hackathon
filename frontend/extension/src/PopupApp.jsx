import { useEffect, useState } from 'react';
import ScoreRing from '../../src/components/ScoreRing.jsx';
import { formatScore, signalLabel } from '../../src/services/format.js';
import logo from '../../public/favicon.svg';
import { analyzePage, listCampaigns } from './analysisClient.js';
import { formatDuration, requestYoutubeContext } from './youtubeContext.js';
import TabCaptureCard from './TabCaptureCard.jsx';
import { getActions, getSavedMode, openTab, readCurrentPage, saveMode, toggleAction } from './browserApi.js';
import { DASHBOARD_URLS } from './config.js';
import { DEMO_SCENARIOS } from './demoData.js';

const PLATFORM_LABELS = { x: 'X', youtube: 'YouTube', instagram: 'Instagram', unknown: 'Unknown' };
const CONTENT_LABELS = { video: 'Video', image: 'Image', text: 'Text', mixed: 'Mixed', none: 'None' };
const RISK_LABELS = {
  high: 'High synthetic-media risk',
  medium: 'Possible manipulation',
  low: 'Low synthetic-media risk',
};
const DETECTION_NOTE = 'Detection is probabilistic and may produce false positives or false negatives.';
const MAX_EVIDENCE_SHOWN = 6;

const dashboardUrl = (mode, path) => `${DASHBOARD_URLS[mode]}${path}`;

const campaignName = (campaign) => `${campaign.source_file ?? campaign.campaign_id} (${campaign.post_count} posts)`;

function CampaignPicker({ campaigns, campaignId, onChange }) {
  if (campaigns.error) return <p className="muted small popup-note">The Veritas API can't be reached, so campaigns can't be listed.</p>;
  if (!campaigns.items) return <p className="muted small popup-note">Loading campaigns...</p>;
  if (campaigns.items.length === 0) {
    return <p className="muted small popup-note">No campaigns imported yet. Import one in the Veritas dashboard to check for related posts.</p>;
  }
  const selected = campaigns.items.find((campaign) => campaign.campaign_id === campaignId);
  return (
    <section className="demo-panel live-panel">
      <label>
        Compare against
        <select value={campaignId ?? ''} onChange={(event) => onChange(event.target.value)}>
          {campaigns.items.map((campaign) => (
            <option key={campaign.campaign_id} value={campaign.campaign_id}>
              {campaignName(campaign)}
            </option>
          ))}
        </select>
      </label>
      {selected?.provenance === 'synthetic_demo_data' && <p>This campaign is fictional, so a match isn't evidence about real activity.</p>}
    </section>
  );
}

function Header({ mode, disabled, onModeChange }) {
  return (
    <header className="popup-header">
      <img src={logo} width="30" height="30" alt="" />
      <div className="popup-brand">
        <strong>VERITAS AI</strong>
        <span className="eyebrow">Social media forensics</span>
      </div>
      <div className="mode-toggle" role="group" aria-label="Analysis mode">
        {['demo', 'live'].map((value) => (
          <button key={value} type="button" disabled={disabled} aria-pressed={mode === value} onClick={() => onModeChange(value)}>
            {value === 'demo' ? 'Demo' : 'Live'}
          </button>
        ))}
      </div>
    </header>
  );
}

function PageSummary({ page }) {
  return (
    <dl className="page-summary">
      <div>
        <dt>Platform</dt>
        <dd>{PLATFORM_LABELS[page.platform] ?? 'Unknown'}</dd>
      </div>
      <div>
        <dt>Content</dt>
        <dd>{CONTENT_LABELS[page.content_type] ?? 'None'}</dd>
      </div>
    </dl>
  );
}

function YouTubeListing({ page, mode }) {
  const [listing, setListing] = useState({ phase: 'idle', context: null, error: '' });
  if (page?.platform !== 'youtube' || !page.video_id) return null;
  const lookUp = async () => {
    setListing({ phase: 'loading', context: null, error: '' });
    const result = await requestYoutubeContext(page.url);
    if (!result.ok) {
      const error =
        result.error === 'youtube_connector_not_configured'
          ? 'The backend has no YouTube API key, so the listing cannot be loaded.'
          : result.error === 'youtube_video_not_found'
            ? 'YouTube did not return this video.'
            : 'The YouTube listing could not be loaded.';
      setListing({ phase: 'error', context: null, error });
      return;
    }
    setListing({ phase: 'ready', context: result.context, error: '' });
  };
  const metadata = listing.context?.metadata;
  return (
    <section className="popup-card">
      <span className="eyebrow">YouTube listing</span>
      <p className="muted small">
        This loads the public title and channel for this video. It does not change the face-score result, and it does not include a verification badge or a Hotstar rating.
      </p>
      {mode !== 'live' && <p className="muted small">Switch to Live before looking up the listing. Demo mode does not leave the browser.</p>}
      {mode === 'live' && (
        <button type="button" className="button button-secondary" onClick={lookUp} disabled={listing.phase === 'loading'}>
          {listing.phase === 'loading' ? 'Looking up…' : 'Look up this video'}
        </button>
      )}
      {listing.error && <p className="notice notice-error">{listing.error}</p>}
      {metadata && (
        <dl className="page-summary">
          <div>
            <dt>Title</dt>
            <dd>{metadata.title ?? 'Not returned'}</dd>
          </div>
          <div>
            <dt>Channel</dt>
            <dd>{metadata.channel_title ?? 'Not returned'}</dd>
          </div>
          <div>
            <dt>Published</dt>
            <dd>{metadata.published_at ?? 'Not returned'}</dd>
          </div>
          <div>
            <dt>Duration</dt>
            <dd>{formatDuration(metadata.duration) ?? 'Not returned'}</dd>
          </div>
        </dl>
      )}
    </section>
  );
}

function IdleView({ page, mode, demoScenario, onDemoScenario, onAnalyze, campaigns, campaignId, onCampaign }) {
  const youtube = page?.platform === 'youtube' && page.video_id;
  const xPending = page?.integration === 'pending_x_api';
  const instagramRemoved = page?.integration === 'instagram_removed';
  return (
    <>
      <section className="popup-card">
        <span className="eyebrow">Current tab</span>
        {!page && <p className="popup-message">Veritas can't read this tab's URL.</p>}
        {xPending && (
          <p className="popup-message">
            Integration pending. X page content is not read. An X investigation will use the official backend X API when that connector exists.
          </p>
        )}
        {instagramRemoved && <p className="popup-message">Instagram page extraction has been removed. This extension does not read Instagram pages.</p>}
        {youtube && (
          <>
            <PageSummary page={{ ...page, content_type: 'none' }} />
            <p className="popup-message">
              Video <span className="mono">{page.video_id}</span>
            </p>
            <p className="muted small">
              Opening this popup does not read the page or store browsing history. Audiovisual content is not retrieved.
            </p>
          </>
        )}
        {page && !youtube && !xPending && !instagramRemoved && (
          <p className="popup-message">This tab is not a single YouTube video. X and Instagram pages are not read.</p>
        )}
      </section>

      {mode === 'demo' && (
        <section className="demo-panel">
          <span className="demo-pill">Demo</span>
          <p>Nothing leaves your browser. This sample is fictional and is not an assessment of the current tab.</p>
          <label>
            Sample response
            <select value={demoScenario} onChange={(event) => onDemoScenario(event.target.value)}>
              {Object.entries(DEMO_SCENARIOS).map(([key, scenario]) => (
                <option key={key} value={key}>
                  {scenario.label}
                </option>
              ))}
            </select>
          </label>
          <button type="button" className="button button-secondary" onClick={onAnalyze}>
            Show labeled sample
          </button>
        </section>
      )}

      {youtube && <YouTubeListing page={page} mode={mode} />}

      {mode === 'live' && youtube && (
        <>
          <CampaignPicker campaigns={campaigns} campaignId={campaignId} onChange={onCampaign} />
          <button type="button" className="button button-primary popup-primary" onClick={onAnalyze} disabled={!campaignId}>
            Compare this URL with the campaign
          </button>
          {!campaignId && <p className="muted small popup-note">Import a campaign before comparing this video URL.</p>}
        </>
      )}

      <div className="popup-actions">
        <button type="button" className="button button-primary" onClick={() => openTab(dashboardUrl(mode, '/'))}>
          Open Veritas
        </button>
        <button type="button" className="button button-secondary" onClick={() => openTab(dashboardUrl(mode, '/campaigns'))}>
          Open campaigns
        </button>
      </div>
    </>
  );
}

function AnalyzingView() {
  return (
    <section className="popup-card" role="status">
      <span className="eyebrow">Analyzing content</span>
      <div className="spinner" aria-hidden="true" />
      <ul className="analyzing-steps">
        <li>Extracting page signals...</li>
        <li>Checking available media...</li>
        <li>Checking related content...</li>
      </ul>
    </section>
  );
}

function MediaSignals({ media }) {
  let headline = RISK_LABELS[media.risk_level] ?? 'Inconclusive';
  if (media.status === 'no_media') headline = 'No media detected';
  if (media.status === 'unsupported') headline = 'Media not supported';
  if (media.status === 'inconclusive') headline = 'Detection inconclusive';
  if (media.status === 'not_available') {
    return (
      <section className="popup-card">
        <span className="eyebrow">Media signals</span>
        <p className="result-title">Media analysis not available</p>
        <p className="muted small">No detector ran on this page. NO SCORE.</p>
      </section>
    );
  }
  const hasScore = typeof media.score === 'number';

  return (
    <section className="popup-card">
      <span className="eyebrow">Media signals</span>
      <div className="media-result">
        {media.status !== 'no_media' && (
          <ScoreRing value={media.score} center={hasScore ? formatScore(media.score) : 'NO SCORE'} label={hasScore ? 'raw output' : ''} tone={media.risk_level} />
        )}
        <div>
          <strong className="result-title">{headline}</strong>
          {media.status !== 'no_media' && (
            <p className="muted small">{hasScore ? 'Raw model output, not a verified probability.' : 'The detector did not return a score.'}</p>
          )}
          {media.model && <p className="mono small muted">{media.model}</p>}
        </div>
      </div>
      <p className="muted small">{DETECTION_NOTE}</p>
    </section>
  );
}

// Two or more kinds of signal must link the post to the same account. Otherwise
// unrelated weak matches with different accounts would add up to a stronger label.
function hasMultiSignalLink(signals) {
  const typesByAccount = new Map();
  signals.forEach((signal) => {
    const account = signal.related_account ?? 'all';
    typesByAccount.set(account, (typesByAccount.get(account) ?? new Set()).add(signal.type));
  });
  return [...typesByAccount.values()].some((types) => types.size >= 2);
}

function DatasetNote({ dataset }) {
  if (!dataset) return null;
  return (
    <>
      <p className="muted small">
        Compared against {dataset.source_file ?? dataset.campaign_id} ({dataset.post_count} posts, {dataset.provenance}).
      </p>
      {dataset.provenance === 'synthetic_demo_data' && (
        <p className="dataset-warning small">This dataset is fictional, so a match isn't evidence about real activity.</p>
      )}
    </>
  );
}

function CoordinationSignals({ coordination, dataset }) {
  const { status, signals, related_post_count: count } = coordination;
  let summary = 'Related content was not checked.';
  if (status === 'none_found') summary = 'No coordination relationships were identified in the available dataset.';
  if (status === 'signals_found') {
    summary = hasMultiSignalLink(signals) ? 'Possible coordinated dissemination' : 'Coordination signals detected';
  }

  return (
    <section className="popup-card">
      <span className="eyebrow">Coordination signals</span>
      <DatasetNote dataset={dataset} />
      {count !== null && status === 'signals_found' && (
        <p className="related-count">
          <strong>{count}</strong> related {count === 1 ? 'post' : 'posts'}
        </p>
      )}
      {signals.length > 0 && (
        <ul className="signal-list">
          {[...new Set(signals.map((signal) => signal.type))].map((type) => (
            <li key={type}>✓ {signalLabel(type)}</li>
          ))}
        </ul>
      )}
      <p className={status === 'signals_found' ? 'result-title' : 'popup-message'}>{summary}</p>
      {status === 'signals_found' && <p className="muted small">Observed similarity. This doesn't establish intent or prove coordination.</p>}
    </section>
  );
}

function Evidence({ result }) {
  const { signals } = result.coordination;
  return (
    <section className="popup-card">
      <span className="eyebrow">Evidence</span>
      {signals.length === 0 ? (
        <p className="popup-message">Insufficient evidence.</p>
      ) : (
        <ul className="evidence-list">
          {signals.slice(0, MAX_EVIDENCE_SHOWN).map((signal) => (
            <li key={`${signal.type}-${signal.evidence}`}>
              <strong>{signalLabel(signal.type)}</strong>
              <span>{signal.evidence}</span>
              {signal.post_ids?.length > 0 && <span className="mono small muted">{signal.post_ids.join(', ')}</span>}
            </li>
          ))}
        </ul>
      )}
      {signals.length > MAX_EVIDENCE_SHOWN && (
        <p className="muted small">{signals.length - MAX_EVIDENCE_SHOWN} more in the full investigation.</p>
      )}
      {result.limitations.length > 0 && (
        <>
          <h3>Limitations</h3>
          <ul className="popup-limitations">
            {result.limitations.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

function ResultActions({ result, page, mode, onReset }) {
  const [saved, setSaved] = useState({ flagged: false, watchlist: false });

  useEffect(() => {
    getActions().then((all) => {
      const has = (key) => (all[key] ?? []).some((item) => item.url === page.url);
      setSaved({ flagged: has('flagged'), watchlist: has('watchlist') });
    });
  }, [page.url]);

  const toggle = async (key) => {
    const isSaved = await toggleAction(key, page.url, { platform: page.platform, analysis_id: result.analysis_id });
    setSaved((current) => ({ ...current, [key]: isSaved }));
  };

  const { campaign_id: campaignId } = result;
  return (
    <section className="result-actions">
      <button
        type="button"
        className="button button-primary popup-primary"
        disabled={!campaignId}
        onClick={() => openTab(dashboardUrl(mode, `/campaigns/${encodeURIComponent(campaignId)}?from=extension`))}
      >
        OPEN FULL INVESTIGATION
      </button>
      {!campaignId && <p className="muted small popup-note">No investigation is linked to this result.</p>}
      <div className="popup-actions">
        <button type="button" className="button button-secondary" aria-pressed={saved.flagged} onClick={() => toggle('flagged')}>
          {saved.flagged ? 'Flagged for review ✓' : 'Flag for Review'}
        </button>
        <button type="button" className="button button-secondary" aria-pressed={saved.watchlist} onClick={() => toggle('watchlist')}>
          {saved.watchlist ? 'On watchlist ✓' : 'Add to Watchlist'}
        </button>
        <button type="button" className="button button-secondary" disabled>
          Generate Evidence Report
        </button>
        <p className="muted small popup-note">Evidence reports stay unavailable in the popup. This button does not request a report.</p>
      </div>
      <p className="muted small popup-note">Flags and the watchlist are saved only in this browser. Nothing is reported to any platform.</p>
      <button type="button" className="link-button small" onClick={onReset}>
        Back
      </button>
    </section>
  );
}

function ResultView({ result, page, mode, onReset }) {
  return (
    <>
      {result.provenance === 'synthetic_demo_data' && (
        <div className="demo-panel demo-result">
          <span className="demo-pill">Synthetic demo data</span>
          <p>Fictional sample. It says nothing about the page you're viewing.</p>
        </div>
      )}
      {result.status === 'insufficient_evidence' && <p className="popup-card result-title">Insufficient evidence</p>}
      <MediaSignals media={result.media} />
      <CoordinationSignals coordination={result.coordination} dataset={result.dataset} />
      <Evidence result={result} />
      <ResultActions result={result} page={page} mode={mode} onReset={onReset} />
    </>
  );
}

export default function PopupApp() {
  const [loadingPage, setLoadingPage] = useState(true);
  const [page, setPage] = useState(null);
  const [mode, setMode] = useState('demo');
  const [demoScenario, setDemoScenario] = useState('signals');
  const [view, setView] = useState('idle');
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [campaigns, setCampaigns] = useState({ items: null, error: false });
  const [campaignId, setCampaignId] = useState(null);

  useEffect(() => {
    Promise.all([readCurrentPage(), getSavedMode()])
      .then(([currentPage, savedMode]) => {
        setPage(currentPage);
        setMode(savedMode);
      })
      .finally(() => setLoadingPage(false));
  }, []);

  // Demo mode must not touch the network, so campaigns load only in Live mode.
  useEffect(() => {
    if (mode !== 'live') return undefined;
    let current = true;
    setCampaigns({ items: null, error: false });
    listCampaigns()
      .then((items) => {
        if (!current) return;
        setCampaigns({ items, error: false });
        setCampaignId(items[0]?.campaign_id ?? null);
      })
      .catch(() => {
        if (!current) return;
        setCampaigns({ items: [], error: true });
        setCampaignId(null);
      });
    return () => {
      current = false;
    };
  }, [mode]);

  const reset = () => {
    setView('idle');
    setResult(null);
    setError(null);
  };

  const changeMode = (nextMode) => {
    setMode(nextMode);
    saveMode(nextMode);
    reset();
  };

  const analyze = async () => {
    setView('analyzing');
    setError(null);
    try {
      setResult(await analyzePage(page, { mode, demoScenario, campaignId }));
      setView('result');
    } catch (failure) {
      setError(failure.message);
      setView('error');
    }
  };

  return (
    <div className="popup">
      <Header mode={mode} disabled={view === 'analyzing'} onModeChange={changeMode} />
      {!loadingPage && <TabCaptureCard />}
      {loadingPage && <p className="popup-message">Checking this page...</p>}
      {!loadingPage && view === 'idle' && (
        <IdleView
          page={page}
          mode={mode}
          demoScenario={demoScenario}
          onDemoScenario={setDemoScenario}
          onAnalyze={analyze}
          campaigns={campaigns}
          campaignId={campaignId}
          onCampaign={setCampaignId}
        />
      )}
      {view === 'analyzing' && <AnalyzingView />}
      {view === 'result' && <ResultView result={result} page={page} mode={mode} onReset={reset} />}
      {view === 'error' && (
        <>
          <div className="notice notice-error" role="alert">
            {error}
          </div>
          <div className="popup-actions">
            <button type="button" className="button button-primary" onClick={analyze}>
              Try again
            </button>
            <button type="button" className="button button-secondary" onClick={reset}>
              Back
            </button>
          </div>
        </>
      )}
    </div>
  );
}
