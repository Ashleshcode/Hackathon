const RADIUS = 56;
const LENGTH = 2 * Math.PI * RADIUS;
const TONES = {
  fake: 'var(--flagged-line)',
  high: 'var(--flagged-line)',
  medium: 'var(--flagged-line)',
  real: 'var(--clear-line)',
  low: 'var(--clear-line)',
};

// With no value the ring is dashed and empty, so it can't be read as a score of 0.
export default function ScoreRing({ value, center, label, tone }) {
  const hasValue = typeof value === 'number';
  const fraction = hasValue ? Math.min(Math.max(value, 0), 1) : 0;
  return (
    <div className="ring">
      <svg viewBox="0 0 132 132" aria-hidden="true">
        <circle cx="66" cy="66" r={RADIUS} fill="none" stroke="var(--rule)" strokeWidth="10" strokeDasharray={hasValue ? undefined : '6 8'} />
        {hasValue && (
          <circle
            cx="66"
            cy="66"
            r={RADIUS}
            fill="none"
            stroke={TONES[tone] ?? 'var(--blue)'}
            strokeWidth="10"
            strokeLinecap="round"
            strokeDasharray={`${fraction * LENGTH} ${LENGTH}`}
          />
        )}
      </svg>
      <div className="ring-center">
        <span className={`ring-value${hasValue ? '' : ' is-empty'}`}>{center}</span>
        <span className="ring-label">{label}</span>
      </div>
    </div>
  );
}
