import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ErrorNotice, Loading, Meta, PageHeader } from '../components/Common.jsx';
import PropagationGraph from '../components/PropagationGraph.jsx';
import { getDisseminationCase, getDisseminationGraph, listDisseminationCases, USE_MOCKS } from '../services/api.js';
import { delayLabel } from '../services/propagationElements.js';
import { useAsync } from '../services/useAsync.js';

function formatMetric(value) {
  if (value === null || value === undefined) return 'Not available';
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(2);
  return String(value);
}

export default function DisseminationPage() {
  const { caseId } = useParams();
  const list = useAsync(() => listDisseminationCases(), []);
  const detail = useAsync(() => (caseId ? getDisseminationCase(caseId) : Promise.resolve(null)), [caseId]);
  const graph = useAsync(() => (caseId ? getDisseminationGraph(caseId) : Promise.resolve(null)), [caseId]);
  const [selection, setSelection] = useState(null);

  const cases = list.data?.cases ?? [];

  return (
    <>
      <PageHeader eyebrow="Dissemination" title="Historical propagation">
        Twitter15 and Twitter16 trees. An arrow goes from the parent post to the child post. Reply text is not in the dataset.
      </PageHeader>
      {USE_MOCKS && (
        <section className="card notice notice-pending" role="status">
          <h2>No historical records are loaded in this view</h2>
          <p>Demo mode does not invent propagation trees or post text. Import a local Twitter15 or Twitter16 directory, then open this page with the API.</p>
        </section>
      )}
      {list.loading && <Loading>Loading propagation cases…</Loading>}
      {list.error && <ErrorNotice>{list.error}</ErrorNotice>}
      {!list.loading && !USE_MOCKS && cases.length === 0 && (
        <section className="card">
          <h2>No imported trees</h2>
          <p>Run the offline importer against a local copy of the dataset. The application does not download it.</p>
        </section>
      )}
      {cases.length > 0 && (
        <div className="dissemination-layout">
          <section className="card">
            <h2>Source posts</h2>
            <ul className="case-list">
              {cases.map((item) => (
                <li key={item.case_id}>
                  <Link to={`/dissemination/${encodeURIComponent(item.case_id)}`}>
                    <span className="mono">{item.source_tweet_id}</span>
                    <span>{item.dataset_name}</span>
                    <span>{item.label ?? 'No label'}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
          {caseId && (
            <section className="card">
              {detail.loading && <Loading>Loading case…</Loading>}
              {detail.error && <ErrorNotice>{detail.error}</ErrorNotice>}
              {detail.data && (
                <>
                  <h2>Source {detail.data.source_tweet_id}</h2>
                  <Meta
                    items={[
                      ['Dataset', detail.data.dataset_name],
                      ['Label', detail.data.label ?? 'No label in the dataset'],
                      ['Source user', detail.data.source_user_id],
                      ['Nodes', formatMetric(detail.data.metrics?.node_count)],
                      ['Edges', formatMetric(detail.data.metrics?.edge_count)],
                      ['Maximum depth', formatMetric(detail.data.metrics?.maximum_depth)],
                      ['Branching factor', formatMetric(detail.data.metrics?.branching_factor)],
                      ['Time span (minutes)', formatMetric(detail.data.metrics?.time_span_minutes)],
                    ]}
                  />
                  <h3>Source text</h3>
                  {detail.data.source_text ? <p>{detail.data.source_text}</p> : <p>The dataset does not include text for this source post.</p>}
                  <p className="muted small">Propagated posts are identified by user and post id. Their text was not supplied and is not reconstructed.</p>
                  {detail.data.provenance && (
                    <>
                      <h3>Provenance</h3>
                      <p className="small">
                        {detail.data.provenance.description} Reference: {detail.data.provenance.reference}
                      </p>
                    </>
                  )}
                </>
              )}
              {graph.data && <PropagationGraph graph={graph.data} onSelect={setSelection} />}
              {selection?.kind === 'node' && (
                <div>
                  <h3>{selection.item.is_root ? 'Root post' : 'Propagated post'}</h3>
                  <Meta
                    items={[
                      ['Post', selection.item.tweet_id],
                      ['User', selection.item.user_id],
                      ['Depth', formatMetric(selection.item.depth)],
                      ['Delay', delayLabel(selection.item.post_time_delay_minutes)],
                      ['Text', selection.item.text ?? 'Not included in the dataset'],
                    ]}
                  />
                </div>
              )}
              {selection?.kind === 'edge' && (
                <div>
                  <h3>Parent to child</h3>
                  <p className="mono small">
                    {selection.item.parent_tweet_id} → {selection.item.child_tweet_id}
                  </p>
                  <p className="small">{delayLabel(selection.item.child_delay_minutes)}</p>
                </div>
              )}
            </section>
          )}
        </div>
      )}
    </>
  );
}
