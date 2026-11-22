import { formatTime } from "../../../utils/formatTime.js";

export default function FrameSpeech({ hasSpeech, nearby, shown, onSeek }) {
  if (!hasSpeech) {
    return null;
  }

  return (
    <div className="keyframe-row keyframe-row-speech">
      <span className="keyframe-label">Речь рядом</span>

      {nearby.length ? (
        <div className="keyframe-speech">
          {shown.map((segment, index) => (
            <button
              className="keyframe-speech-row"
              key={`${segment.start}-${index}`}
              onClick={() => onSeek(segment.start)}
            >
              <span className="keyframe-speech-time">
                {formatTime(segment.start)}
              </span>

              <span>{segment.text}</span>
            </button>
          ))}

          {nearby.length > shown.length && (
            <span className="muted">
              +{nearby.length - shown.length} реплик
            </span>
          )}
        </div>
      ) : (
        <span className="muted">
          реплик в окрестности нет
        </span>
      )}
    </div>
  );
}