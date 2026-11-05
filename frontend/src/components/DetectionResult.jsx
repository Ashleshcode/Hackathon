import { formatScore, formatSeconds } from '../services/format.js';
import { Badge, Limitations, Meta } from './Common.jsx';
import Ring from './ScoreRing.jsx';

function ScoreBar({ score }) {
  if (typeof score !== 'number') return <span className="muted">No score</span>;
  return (
    <span className="score-bar">
      <span className="score-track">
        <span className="score-fill" style={{ width: `${Math.min(Math.max(score, 0), 1) * 100}%` }} />
      </span>
      <span className="mono">{formatScore(score)}</span>
    </span>
  );
}

function ImageResult({ result }) {
  return (
    <div className="result-headline">
      <Ring value={result.score} center={formatScore(result.score)} label={(result.score_type ?? 'model output').replaceAll('_', ' ')} tone={result.prediction} />
      <div className="result-copy">
        <span className="eyebrow">Detector prediction</span>
        <Badge value={result.prediction} />
        <p className="muted small">This is the model's raw output. It isn't a verified probability or a finding of fact.</p>
      </div>
    </div>
  );
}

function FrameTable({ frames }) {
  if (!frames?.length) return <p className="muted">No frame results were returned.</p>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Timestamp</th>
            <th>Face</th>
            <th>Prediction</th>
            <th>Score</th>
          </tr>
        </thead>
        <tbody>
          {frames.map((frame) => (
            <tr key={frame.timestamp_seconds}>
              <td className="mono">{formatSeconds(frame.timestamp_seconds)}</td>
              <td>{frame.face_detected ? 'Yes' : 'No'}</td>
              <td>
                <Badge value={frame.prediction} fallback="Not scored" />
              </td>
              <td>
                <ScoreBar score={frame.score} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function VideoResult({ result }) {
  const sampled = result.frames_sampled;
  const usable = result.frames_with_faces;
  const hasFrames = typeof usable === 'number' && sampled > 0;
  return (
    <>
      <div className="result-headline">
        <Ring value={hasFrames ? usable / sampled : null} center={hasFrames ? `${usable}/${sampled}` : 'No frames'} label="usable frames" />
        <div className="result-copy">
          <span className="eyebrow">Video assessment</span>
          <Badge value={result.video_assessment} fallback="inconclusive" />
          <p className="muted small">Based on sampled frames only, so other parts of the video weren't examined.</p>
        </div>
      </div>
      <h3>Sampled frames</h3>
      <FrameTable frames={result.frame_results} />
    </>
  );
}

export default function DetectionResult({ result, fileName }) {
  const isVideo = result.media_type === 'video';
  return (
    <section className="card" aria-label="Detection result">
      {isVideo ? <VideoResult result={result} /> : <ImageResult result={result} />}
      <Limitations items={result.limitations} />
      <Meta
        items={[
          ['Analysis ID', result.analysis_id],
          ['File', fileName],
          ['Status', result.status],
          ['Model', result.model],
          ...(isVideo ? [['Aggregation method', result.aggregation_method]] : []),
          ['Source', result.provenance],
        ]}
      />
    </section>
  );
}
