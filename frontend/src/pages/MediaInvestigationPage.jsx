import { PageHeader } from '../components/Common.jsx';
import { MEDIA_ANALYSIS_PENDING } from '../services/api.js';

export default function MediaInvestigationPage() {
  return (
    <>
      <PageHeader eyebrow="Media" title="Media investigation">
        Upload analysis stays off until a permitted media route exists.
      </PageHeader>
      <section className="card notice notice-pending" role="status">
        <h2>Integration pending</h2>
        <p>{MEDIA_ANALYSIS_PENDING}</p>
        <p className="muted small">The shared detector can be called by the backend test routes. This screen does not upload a file or invent a score.</p>
      </section>
    </>
  );
}
