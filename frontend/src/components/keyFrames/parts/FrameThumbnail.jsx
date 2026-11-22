import { fileUrl } from "../../../utils/fileUrl.js";
import { formatTime } from "../../../utils/formatTime.js";

export default function FrameThumbnail({ frame, onSeek }) {
  if (!frame.artifact) {
    return null;
  }

  return (
    <button
      className="keyframe-thumb"
      onClick={() => onSeek(frame.timestamp)}
      title="Перейти к кадру"
    >
      <img
        src={fileUrl(frame.jobId, frame.artifact)}
        alt={`Кадр ${formatTime(frame.timestamp)}`}
        loading="lazy"
      />

      <span className="keyframe-time">
        {formatTime(frame.timestamp)}
      </span>
    </button>
  );
}