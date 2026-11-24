import { useEffect } from "react";
import FrameCard from "./FrameCard.jsx";

export default function FrameModal({
  job,
  frame,
  index,
  roads,
  ocr,
  speech,
  scenes,
  onSeek,
  onClose,
}) {
  useEffect(() => {
    const handler = (event) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  if (!frame) return null;

  return (
    <div className="frame-modal" role="dialog" aria-modal="true">
      <div className="frame-modal__backdrop" onClick={onClose} />
      <div className="frame-modal__body">
        <button
          type="button"
          className="frame-modal__close"
          onClick={onClose}
          aria-label="Закрыть"
        >
          ×
        </button>

        <FrameCard
          job={job}
          frame={frame}
          index={index}
          offset={0}
          roads={roads}
          ocr={ocr}
          speech={speech}
          scenes={scenes}
          onSeek={onSeek}
        />
      </div>
    </div>
  );
}