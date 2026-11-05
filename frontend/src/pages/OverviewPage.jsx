import { Link } from 'react-router-dom';
import { ErrorNotice, Loading } from '../components/Common.jsx';
import { getOverview } from '../services/api.js';
import { useAsync } from '../services/useAsync.js';

const STATS = [
  ['media_analysed', 'Media analysed', '/media'],
  ['posts_imported', 'Posts imported', '/campaigns'],
  ['campaigns', 'Campaigns', '/campaigns'],
  ['investigations', 'Investigations', '/reports'],
];

const CHIPS = ['Image analysis', 'Video frames', 'Coordination graph', 'Evidence reports'];

const POINTS = ['Every link shows its evidence', 'Limitations always disclosed', 'People make the final call'];

const STEPS = [
  ['Analyse media', 'Run images and sampled video frames through a pretrained detector.'],
  ['Map relationships', 'Find repeated media, similar captions and shared links across accounts.'],
  ['Review the evidence', 'Bring the findings together in one report for human review.'],
];

const FEATURES = [
  {
    eyebrow: 'Media',
    title: 'Image and video analysis',
    text: 'See the raw detector output, timestamped frames, and an honest "inconclusive" when there isn\'t enough to assess.',
    to: '/media',
    icon: <path d="M4 5h16v14H4zM4 15l5-4 4 3 3-2 4 3M15 9h.01" />,
  },
  {
    eyebrow: 'Coordination',
    title: 'Campaign graph',
    text: 'Import posts as CSV or JSON, then click any relationship to see exactly why two accounts are linked.',
    to: '/campaigns',
    icon: <path d="M6 7a2 2 0 1 0 0-.01M18 5a2 2 0 1 0 0-.01M12 19a2 2 0 1 0 0-.01M7.6 8.4l3.2 8.2M16.6 6.6l-3.4 10M8 6.2l8-.8" />,
  },
  {
    eyebrow: 'Reporting',
    title: 'Investigation report',
    text: 'Combine media and coordination evidence with limitations and recommended review steps.',
    to: '/reports',
    icon: <path d="M7 3h7l4 4v14H7zM14 3v4h4M10 12h5M10 16h5" />,
  },
  {
    eyebrow: 'Dissemination',
    title: 'Historical propagation',
    text: 'Read a local Twitter15 or Twitter16 tree. Arrows follow the recorded parent-to-child direction.',
    to: '/dissemination',
    icon: <path d="M12 3v10M8 9l4 4 4-4M5 21h14" />,
  },
];

// Decorative network drawing. It doesn't represent any data.
function ProcessArt() {
  const points = [
    [70, 40],
    [130, 74],
    [62, 104],
    [196, 36],
    [226, 96],
    [290, 58],
  ];
  const links = [
    [0, 1],
    [0, 2],
    [1, 2],
    [1, 3],
    [1, 4],
    [3, 5],
    [4, 5],
  ];
  return (
    <svg className="process-art" viewBox="0 0 350 140" aria-hidden="true">
      {links.map(([a, b]) => (
        <line key={`${a}-${b}`} x1={points[a][0]} y1={points[a][1]} x2={points[b][0]} y2={points[b][1]} stroke="#93c5fd" strokeOpacity="0.55" strokeWidth="1.5" />
      ))}
      {points.map(([x, y], index) => (
        <circle key={`${x}-${y}`} cx={x} cy={y} r={index === 1 ? 9 : 6} fill={index === 1 ? '#fff' : '#60a5fa'} />
      ))}
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M5 12.5l4.5 4.5L19 7.5" />
    </svg>
  );
}

function Hero() {
  return (
    <section className="band hero">
      <div className="hero-grid">
        <div>
          <div className="chip-row">
            {CHIPS.map((chip) => (
              <span key={chip} className="hero-chip">
                {chip}
              </span>
            ))}
          </div>
          <h1>
            Fake content spreads fast. <span className="hero-accent">Follow the evidence.</span>
          </h1>
          <p className="hero-lede">
            Veritas AI helps investigators check suspicious images and videos, spot coordinated posting across accounts,
            and build a report based on what was actually observed.
          </p>
          <div className="hero-actions">
            <Link to="/media" className="button button-secondary">
              Media status
            </Link>
            <Link to="/campaigns" className="button button-secondary">
              Import posts
            </Link>
          </div>
          <ul className="hero-points">
            {POINTS.map((point) => (
              <li key={point}>
                <CheckIcon /> {point}
              </li>
            ))}
          </ul>
        </div>
        <ol className="process-panel">
          <ProcessArt />
          {STEPS.map(([title, text], index) => (
            <li key={title} className="process-step">
              <span className="process-number">{index + 1}</span>
              <div>
                <strong>{title}</strong>
                <span>{text}</span>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

function WorkspaceStats({ loading, data, error }) {
  return (
    <section className="band stats-band">
      <span className="eyebrow">Your workspace</span>
      <h2>Current investigation activity</h2>
      {loading && <Loading />}
      {error && <ErrorNotice>Couldn't load workspace activity: {error}</ErrorNotice>}
      {data && (
        <div className="stat-grid">
          {STATS.map(([key, label, href]) => (
            <Link key={key} to={href} className="stat">
              {typeof data[key] === 'number' ? (
                <span className="stat-value">{data[key]}</span>
              ) : (
                <span className="stat-value stat-empty">Not connected</span>
              )}
              <span className="stat-label">{label}</span>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}

export default function OverviewPage() {
  const { loading, data, error } = useAsync(getOverview, []);

  return (
    <>
      <Hero />
      <WorkspaceStats loading={loading} data={data} error={error} />

      <div className="section-heading">
        <span className="eyebrow">One workflow</span>
        <h2>From a single file to a full picture</h2>
      </div>
      <div className="feature-grid">
        {FEATURES.map((feature) => (
          <Link key={feature.title} to={feature.to} className="card feature">
            <span className="feature-icon">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                {feature.icon}
              </svg>
            </span>
            <span className="eyebrow">{feature.eyebrow}</span>
            <h3>{feature.title}</h3>
            <p>{feature.text}</p>
          </Link>
        ))}
      </div>

      {data && (
        <section className="card">
          <h2>Recent activity</h2>
          {data.recent?.length ? (
            <ul className="activity-list">
              {data.recent.map((item) => (
                <li key={item.id}>
                  <span className="muted small">{item.kind}</span>
                  <Link to={item.href} className="mono">
                    {item.id}
                  </Link>
                  <span>{item.description}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">Nothing yet. Import a campaign to see it here. Media analysis and reports are not connected.</p>
          )}
        </section>
      )}
    </>
  );
}
