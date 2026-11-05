const BADGE_TONES = {
  fake: 'flagged',
  real: 'clear',
  completed: 'neutral',
};

export function Badge({ value, fallback = 'No prediction' }) {
  const text = value ?? fallback;
  return <span className={`badge badge-${BADGE_TONES[value] ?? 'muted'}`}>{text}</span>;
}

export function PageHeader({ eyebrow, title, children }) {
  return (
    <header className="page-header">
      {eyebrow && <span className="eyebrow">{eyebrow}</span>}
      <h1>{title}</h1>
      {children && <p>{children}</p>}
    </header>
  );
}

export function Limitations({ items }) {
  if (!items?.length) return null;
  return (
    <section className="limitations">
      <h3>Limitations</h3>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}

export function ErrorNotice({ children }) {
  return (
    <div className="notice notice-error" role="alert">
      {children}
    </div>
  );
}

export function Loading({ children = 'Loading…' }) {
  return (
    <p className="muted" role="status">
      {children}
    </p>
  );
}

export function Meta({ items }) {
  return (
    <dl className="meta">
      {items.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value ?? 'Not provided'}</dd>
        </div>
      ))}
    </dl>
  );
}
