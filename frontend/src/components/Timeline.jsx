import { formatTime } from "../utils/formatTime.js";

export default function Timeline({ observations, duration, onSeek }) {
  return (
    <div className="timeline">
      {observations.filter((item) => ["speech", "ocr", "scene"].includes(item.source)).map((item) => (
        <button key={item.id} className={`marker marker-${item.source}`} style={{ left: `${duration ? Math.min(99, (item.start / duration) * 100) : 0}%` }} title={`${formatTime(item.start)}: ${item.text}`} onClick={() => onSeek(item.start)} aria-label={`Перейти: ${item.text}`} />
      ))}
    </div>
  );
}
