import { useCallback, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { ErrorNotice, Loading, Meta, PageHeader } from '../components/Common.jsx';
import InvestigatorAssessment from '../components/InvestigatorAssessment.jsx';
import NetworkGraph from '../components/NetworkGraph.jsx';
import UploadPanel from '../components/UploadPanel.jsx';
import { getCampaign, getCampaignGraph, importCampaign, USE_MOCKS } from '../services/api.js';
import { formatTimestamp, safeUrl, signalLabel } from '../services/format.js';
import { clusterColor, platformShapes, UNCLUSTERED_COLOR } from '../services/graphElements.js';
import { CAMPAIGN_SCENARIOS } from '../services/mockData.js';
import { useAsync } from '../services/useAsync.js';

const SOURCE_TYPES = [
  ['uploaded_dataset', 'Uploaded dataset'],
  ['curated_sample', 'Curated sample'],
  ['synthetic_demo_data', 'Synthetic demo data'],
];

function ImportSummary({ campaign }) {
  const summary = campaign.import_summary ?? {};
  const errors = summary.errors ?? [];
  const platforms = Object.entries(summary.platforms ?? {});
  return (
    <section className="card">
      <h2>Import summary</h2>
      <Meta
        items={[
          ['Campaign ID', campaign.campaign_id],
          ['Source', campaign.provenance],
          ['File', campaign.source_file],
          ['Records accepted', `${summary.accepted ?? 0} of ${summary.total_records ?? 0}`],
          ['Platforms', platforms.map(([name, count]) => `${name} (${count})`).join(', ') || 'None'],
        ]}
      />
      {errors.length > 0 && (
        <details className="row-errors" open>
          <summary>
            {errors.length} {errors.length === 1 ? 'row' : 'rows'} rejected
          </summary>
          <ul>
            {errors.map((error) => (
              <li key={`${error.row}-${error.message}`}>
                <span className="mono">Row {error.row}:</span> {error.message}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

function EvidencePanel({ selection, graph, posts }) {
  const clusters = graph.clusters ?? [];

  if (selection?.kind === 'edge') {
    const { source, target, signals = [] } = selection.item;
    const nameOf = (id) => graph.nodes.find((node) => node.id === id)?.label ?? id;
    return (
      <>
        <h3>Relationship</h3>
        <p className="mono small">
          {nameOf(source)} and {nameOf(target)}
        </p>
        <ul className="evidence-list">
          {signals.map((signal) => (
            <li key={`${signal.type}-${signal.evidence}`}>
              <strong>{signalLabel(signal.type)}</strong>
              <span>{signal.evidence}</span>
              {signal.post_ids?.length > 0 && <span className="mono small muted">{signal.post_ids.join(', ')}</span>}
            </li>
          ))}
        </ul>
        <p className="muted small">An observed similarity, not proof of coordination or intent.</p>
      </>
    );
  }

  if (selection?.kind === 'node') {
    const node = selection.item;
    const accountPosts = posts.filter((post) => post.account_id === node.account_id && post.platform === node.platform);
    return (
      <>
        <h3>Account</h3>
        <p className="mono small">{node.label}</p>
        <Meta
          items={[
            ['Platform', node.platform],
            ['Cluster', node.cluster_id ?? 'None'],
          ]}
        />
        {accountPosts.length > 0 && (
          <ul className="evidence-list">
            {accountPosts.map((post) => (
              <li key={post.post_id}>
                <span className="mono small muted">
                  {post.post_id}, {formatTimestamp(post.timestamp)}
                </span>
                <span>{post.text}</span>
              </li>
            ))}
          </ul>
        )}
      </>
    );
  }

  return (
    <>
      <h3>Clusters</h3>
      {clusters.length === 0 ? (
        <p className="muted small">No clusters found.</p>
      ) : (
        <ul className="evidence-list">
          {clusters.map((cluster) => (
            <li key={cluster.cluster_id}>
              <strong>
                <span className="swatch" style={{ background: clusterColor(cluster.cluster_id, clusters) }} />
                {cluster.cluster_id}
              </strong>
              <span className="muted small">{cluster.account_ids?.length ?? 0} accounts</span>
              <span>{cluster.summary}</span>
            </li>
          ))}
        </ul>
      )}
      <p className="muted small">Select an account or relationship in the graph to see its evidence.</p>
    </>
  );
}

function GraphLegend({ graph }) {
  return (
    <div className="legend">
      {platformShapes(graph.nodes).map(({ platform, shape }) => (
        <span key={platform}>
          <span className={`shape shape-${shape}`} /> {platform}
        </span>
      ))}
      <span>
        <span className="swatch" style={{ background: UNCLUSTERED_COLOR }} /> Not in a cluster
      </span>
      {graph.nodes.some((node) => node.is_checked_post) && (
        <span>
          <span className="shape shape-ellipse shape-checked" /> Checked from the extension
        </span>
      )}
      <span>Thicker line: more signals</span>
    </div>
  );
}

function PostTable({ posts }) {
  if (posts.length === 0) return <p className="muted">No post records to show.</p>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Post</th>
            <th>Platform</th>
            <th>Account</th>
            <th>Posted</th>
            <th>Text</th>
            <th>Media hash</th>
          </tr>
        </thead>
        <tbody>
          {posts.map((post) => {
            const url = safeUrl(post.url);
            return (
              <tr key={post.post_id}>
                <td className="mono">
                  {url ? (
                    <a href={url} target="_blank" rel="noopener noreferrer">
                      {post.post_id}
                    </a>
                  ) : (
                    post.post_id
                  )}
                </td>
                <td>{post.platform}</td>
                <td className="mono">{post.account_id}</td>
                <td className="nowrap">{formatTimestamp(post.timestamp)}</td>
                <td className="wide-cell">{post.text}</td>
                <td className="mono">{post.media_hash ?? 'None'}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

const TIMELINE_LIMIT = 100;

function PostTimeline({ posts }) {
  if (posts.length === 0) return <p className="muted">No post records to show.</p>;
  // Posts with no known time go last rather than appearing to be the earliest.
  const timeOf = (post) => (post.timestamp ? new Date(post.timestamp).getTime() : Infinity);
  const ordered = [...posts].sort((a, b) => (timeOf(a) === timeOf(b) ? 0 : timeOf(a) - timeOf(b)));
  return (
    <>
      <ol className="timeline">
        {ordered.slice(0, TIMELINE_LIMIT).map((post) => (
          <li key={`${post.platform}-${post.post_id}`}>
            <span className="mono small muted">{formatTimestamp(post.timestamp)}</span>
            <span>
              <span className="mono">{post.account_id}</span> <span className="muted small">on {post.platform}</span>
            </span>
            {post.text && <span className="small">{post.text}</span>}
          </li>
        ))}
      </ol>
      {ordered.length > TIMELINE_LIMIT && <p className="muted small">Showing the earliest {TIMELINE_LIMIT} of {ordered.length} posts.</p>}
    </>
  );
}

function CampaignDetail({ campaignId }) {
  const [selection, setSelection] = useState(null);
  const load = useCallback(
    () => Promise.all([getCampaign(campaignId), getCampaignGraph(campaignId)]),
    [campaignId],
  );
  const { loading, data, error } = useAsync(load, [load]);

  if (loading) return <Loading>Loading campaign…</Loading>;
  if (error) return <ErrorNotice>Couldn't load this campaign: {error}</ErrorNotice>;

  const [campaign, graph] = data;
  const posts = campaign.posts ?? [];

  const checkedPost = campaign.extension_post;
  const checkedUrl = checkedPost ? safeUrl(checkedPost.url) : null;

  return (
    <>
      {checkedPost && (
        <div className="notice notice-checked">
          <strong>This view adds one post from the browser extension</strong> to campaign{' '}
          <span className="mono">{campaign.parent_campaign_id}</span>.{' '}
          {checkedUrl ? (
            <a href={checkedUrl} target="_blank" rel="noopener noreferrer">
              View source page
            </a>
          ) : (
            'Source page unavailable.'
          )}
          . It was read from a public page, isn't part of the imported dataset, and the original campaign is unchanged.
          {campaign.provenance === 'synthetic_demo_data' && " The dataset it's compared with is fictional, so a match isn't evidence about real activity."}
        </div>
      )}
      <ImportSummary campaign={campaign} />
      <section className="card">
        <h2>Relationship graph</h2>
        <GraphLegend graph={graph} />
        <div className="graph-layout">
          <div className="graph-area">
            <NetworkGraph graph={graph} onSelect={setSelection} />
          </div>
          <aside className="evidence-panel" aria-live="polite">
            <EvidencePanel selection={selection} graph={graph} posts={posts} />
          </aside>
        </div>
      </section>
      <section className="card">
        <h2>Timeline</h2>
        <PostTimeline posts={posts} />
      </section>
      <section className="card">
        <h2>Posts</h2>
        <PostTable posts={posts} />
      </section>
      <InvestigatorAssessment campaignId={campaignId} />
    </>
  );
}

export default function CampaignAnalysisPage() {
  const { campaignId } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [sourceType, setSourceType] = useState('uploaded_dataset');
  const [mockScenario, setMockScenario] = useState('C001');
  const [progress, setProgress] = useState(null);
  const [error, setError] = useState(null);

  const runImport = async (file) => {
    setError(null);
    setProgress(0);
    try {
      const campaign = await importCampaign(file, sourceType, { onProgress: setProgress, mockScenario });
      navigate(`/campaigns/${encodeURIComponent(campaign.campaign_id)}`);
    } catch (failure) {
      setError(failure.message);
    } finally {
      setProgress(null);
    }
  };

  const busy = progress !== null;

  return (
    <>
      <PageHeader eyebrow="Coordination" title="Campaign analysis">
        Import post records as CSV or JSON to see how accounts relate and what evidence supports each link.
      </PageHeader>

      {searchParams.get('from') === 'extension' && (
        <div className="review-banner">
          <strong>Opened from the Veritas extension</strong>
          <span>Review the relationships and evidence below. Any conclusion is yours to make.</span>
        </div>
      )}

      <section className="card">
        <UploadPanel
          accept=".csv,.json,text/csv,application/json"
          hint="or drop a CSV or JSON file here"
          disabled={busy}
          progress={progress ?? 0}
          busyLabel="Building graph…"
          onFile={runImport}
        />
        <div className="control-row">
          <label className="mock-control">
            Data source
            <select value={sourceType} disabled={busy} onChange={(event) => setSourceType(event.target.value)}>
              {SOURCE_TYPES.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          {USE_MOCKS && (
            <label className="mock-control">
              Mock response
              <select value={mockScenario} disabled={busy} onChange={(event) => setMockScenario(event.target.value)}>
                {Object.entries(CAMPAIGN_SCENARIOS).map(([id, scenario]) => (
                  <option key={id} value={id}>
                    {scenario.label}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
        {USE_MOCKS && (
          <p className="muted small">In mock mode your file isn't read. You'll see the sample response chosen above.</p>
        )}
      </section>

      {error && <ErrorNotice>Import failed: {error}</ErrorNotice>}
      {campaignId && <CampaignDetail key={campaignId} campaignId={campaignId} />}
    </>
  );
}
