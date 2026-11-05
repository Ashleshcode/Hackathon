import { PageHeader } from '../components/Common.jsx';
import { REPORTS_PENDING } from '../services/api.js';

export default function ReportPage() {
  return (
    <>
      <PageHeader eyebrow="Reporting" title="Investigation report">
        Reports stay off until the investigation routes exist.
      </PageHeader>
      <section className="card notice notice-pending" role="status">
        <h2>Integration pending</h2>
        <p>{REPORTS_PENDING}</p>
        <p className="muted small">Campaign evidence remains available from an imported campaign. This screen does not open a sample report.</p>
      </section>
    </>
  );
}
