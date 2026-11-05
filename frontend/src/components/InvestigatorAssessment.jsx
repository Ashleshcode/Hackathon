import { useState } from 'react';

const OPTIONS = [
  'Not yet reviewed',
  'Needs further review',
  'Possible coordinated dissemination',
  'Insufficient evidence',
  'No concern identified',
];

function loadAssessment(key) {
  try {
    return { assessment: OPTIONS[0], notes: '', ...JSON.parse(localStorage.getItem(key)) };
  } catch {
    return { assessment: OPTIONS[0], notes: '' };
  }
}

// The only place a conclusion is recorded, and it is always the investigator's.
export default function InvestigatorAssessment({ campaignId }) {
  const key = `veritas_assessment_${campaignId}`;
  const [value, setValue] = useState(() => loadAssessment(key));

  const update = (changes) => {
    const next = { ...value, ...changes };
    setValue(next);
    try {
      localStorage.setItem(key, JSON.stringify(next));
    } catch {
      // Storage can be blocked. The form still works for this visit.
    }
  };

  return (
    <section className="card assessment">
      <h2>Investigator assessment</h2>
      <label>
        Your assessment
        <select value={value.assessment} onChange={(event) => update({ assessment: event.target.value })}>
          {OPTIONS.map((option) => (
            <option key={option}>{option}</option>
          ))}
        </select>
      </label>
      <label>
        Notes
        <textarea rows="3" value={value.notes} onChange={(event) => update({ notes: event.target.value })} />
      </label>
      <p className="muted small">Set by a person, never by the system. Saved only in this browser.</p>
    </section>
  );
}
