import { formatTime } from "../../../utils/formatTime.js";

export default function FrameHeader({ index, scene }) {
  return (
    <header className="keyframe-head">
      <strong>Кадр {index}</strong>

      {scene && (
        <span className="keyframe-scene">
          Сцена {scene.number}
          {" · "}
          {formatTime(scene.start)}
          –
          {formatTime(scene.end)}
        </span>
      )}
    </header>
  );
}