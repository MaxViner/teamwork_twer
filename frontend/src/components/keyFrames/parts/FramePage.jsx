import FrameCard from "./FrameCard.jsx";

export default function FramePage({
  job,
  onSeek,
  roads,
  ocr,
  speech,
  scenes,
  frames,
  offset,
}) {
  return (
    <div className="keyframe-list">
      {frames.map((frame, index) => (
        <FrameCard
          key={frame.timestamp}
          job={job}
          frame={frame}
          index={index}
          offset={offset}
          roads={roads}
          ocr={ocr}
          speech={speech}
          scenes={scenes}
          onSeek={onSeek}
        />
      ))}
    </div>
  );
}