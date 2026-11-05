import { Link } from 'react-router-dom';
import { formatScore, signalLabel } from '../services/format.js';
import { Badge, Limitations, Meta } from './Common.jsx';

export default function ReportSummary({ report }) {
  const media = report.media_findings ?? [];
  const coordination = report.coordination_findings ?? [];
  const actions = report.recommended_actions ?? [];

  return (
    <>
      <div className="review-banner">
        <strong>Conclusion: pending human review</strong>
        <span>
          This report collects evidence. It doesn't determine whether any media is fake, any claim is false or any
          account is malicious.
        </span>
      </div>

      <section className="card">
        <h2>Media evidence</h2>
        {media.length === 0 && <p className="muted">No media findings in this report.</p>}
        <ul className="finding-list">
          {media.map((finding) => (
            <li key={finding.analysis_id}>
              <div className="finding-head">
                <span className="mono">{finding.analysis_id}</span>
                <span className="muted">{finding.media_type}</span>
                <Badge value={finding.outcome} />
                <span className="mono small">Score: {formatScore(finding.score)}</span>
              </div>
              <p>{finding.detail}</p>
              <p className="muted small">Model: {finding.model ?? 'Not provided'}</p>
            </li>
          ))}
        </ul>
      </section>

      <section className="card">
        <h2>Coordination signals</h2>
        {coordination.length === 0 && <p className="muted">No coordination findings in this report.</p>}
        <ul className="finding-list">
          {coordination.map((finding) => (
            <li key={`${finding.campaign_id}-${finding.cluster_id}`}>
              <div className="finding-head">
                <Link to={`/campaigns/${encodeURIComponent(finding.campaign_id)}`} className="mono">
                  {finding.campaign_id}
                </Link>
                <span className="mono">{finding.cluster_id}</span>
                <span className="muted">{finding.account_count} accounts</span>
              </div>
              <p>{finding.detail}</p>
              <div className="chip-row">
                {(finding.signals ?? []).map((signal) => (
                  <span key={signal} className="chip">
                    {signalLabel(signal)}
                  </span>
                ))}
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section className="card">
        <h2>Recommended review actions</h2>
        {actions.length === 0 ? (
          <p className="muted">No actions were recommended.</p>
        ) : (
          <ol className="action-list">
            {actions.map((action) => (
              <li key={action}>{action}</li>
            ))}
          </ol>
        )}
        <Limitations items={report.limitations} />
        <Meta
          items={[
            ['Report ID', report.report_id],
            ['Status', report.status],
            ['Source', report.provenance],
          ]}
        />
      </section>
    </>
  );
}
