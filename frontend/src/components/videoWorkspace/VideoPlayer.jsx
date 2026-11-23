import { fileUrl } from "../../utils/fileUrl.js";
import { formatTime } from "../../utils/formatTime.js";

export default function VideoPlayer({ jobId, preview, duration, currentTime, videoRef, onSeek, onTimeUpdate }) {
  return (
    <>
      <video key={preview} ref={videoRef} controls preload="metadata" src={fileUrl(jobId, preview)} onTimeUpdate={onTimeUpdate} />
      <div className="time-row"><span>{formatTime(currentTime)}</span><span>{formatTime(duration)}</span></div>
      <input className="scrubber" type="range" min="0" max={Math.max(duration, 0.1)} step="0.1" value={Math.min(currentTime, duration)} onChange={(event) => onSeek(Number(event.target.value))} aria-label="Перемотка видео" />
    </>
  );
}
