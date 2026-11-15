import { fileUrl } from "../utils/fileUrl.js";
import { formatTime } from "../utils/formatTime.js";

export default function FrameGrid({ jobId, frames, onSeek }) {
  return (
    <>
      <h3>Исследованные кадры</h3>
      <div className="frame-grid">
        {frames.map((frame) => (
          <button key={frame.artifact} className="frame" onClick={() => onSeek(frame.timestamp)}>
            <img src={fileUrl(jobId, frame.artifact)} alt={`Кадр ${formatTime(frame.timestamp)}`} loading="lazy" />
            <span>{formatTime(frame.timestamp)}</span>
          </button>
        ))}
      </div>
    </>
  );
}
