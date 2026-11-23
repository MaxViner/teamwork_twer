import { formatTime } from "../../utils/formatTime.js";


export default function Timeline({
  observations,
  speechSegments = [],
  sceneIntervals = [],
  duration,
  onSeek,
}) {
  const position = (start) => (
    duration
      ? Math.min(99, (start / duration) * 100)
      : 0
  );

  const speechMarkers = speechSegments.length > 0
    ? speechSegments
    : observations.filter((item) => item.source === "speech");


  return (
    <div className="timeline">
      {sceneIntervals.map(([start, end], index) => (
        <button
          key={`scene-${index}`}
          className="marker marker-scene"
          style={{ left: `${position(start)}%` }}
          title={`${formatTime(start)} — ${formatTime(end)}: сцена ${index + 1}`}
          onClick={() => onSeek(start)}
          aria-label={`Перейти к сцене ${index + 1}`}
        />
      ))}


      {speechMarkers.map((item, index) => (
        <button
          key={`speech-${index}`}
          className="marker marker-speech"
          style={{ left: `${position(item.start)}%` }}
          title={`${formatTime(item.start)}: ${item.text}`}
          onClick={() => onSeek(item.start)}
          aria-label={`Перейти к реплике ${index + 1}`}
        />
      ))}


      {observations
        .filter((item) => item.source === "ocr")
        .map((item) => (
          <button
            key={item.id}
            className={`marker marker-${item.source}`}
            style={{ left: `${position(item.start)}%` }}
            title={`${formatTime(item.start)}: ${item.text}`}
            onClick={() => onSeek(item.start)}
            aria-label={`Перейти: ${item.text}`}
          />
        ))}
    </div>
  );
}
