import { useMemo } from "react";
import { nearbySpeech, closestSpeech } from "../lib/speech.js";
import { sceneFor } from "../lib/scenes.js";
import { textsForFrame } from "../lib/ocr.js";
import FrameThumbnail from "./FrameThumbnail.jsx";
import FrameHeader from "./FrameHeader.jsx";
import FrameSummary from "./FrameSummary.jsx";
import FrameObjects from "./FrameObjects.jsx";
import FramePlace from "./FramePlace.jsx";
import FrameRoad from "./FrameRoad.jsx";
import FrameTexts from "./FrameTexts.jsx";
import FrameSpeech from "./FrameSpeech.jsx";

export default function FrameCard({
  job,
  frame,
  index,
  offset,
  roads,
  ocr,
  speech,
  scenes,
  onSeek,
}) {
  const objects = useMemo(
    () => [...(frame.objects || [])].sort(
      (a, b) => (
        Number(b.area_percent || 0)
        - Number(a.area_percent || 0)
      ),
    ),
    [frame.objects],
  );

  const scene = useMemo(
    () => sceneFor(scenes, frame.timestamp),
    [scenes, frame.timestamp],
  );

  const road = useMemo(
    () => roads.find(
      (item) => item.artifact === frame.artifact && frame.artifact,
    ) ?? roads.find(
      (item) => Number(item.start) === Number(frame.timestamp),
    ),
    [roads, frame.artifact, frame.timestamp],
  );

  const texts = useMemo(
    () => textsForFrame(ocr, frame),
    [ocr, frame],
  );

  const nearby = useMemo(
    () => nearbySpeech(speech, frame.timestamp),
    [speech, frame.timestamp],
  );

  const shownSpeech = useMemo(
    () => closestSpeech(nearby, frame.timestamp),
    [nearby, frame.timestamp],
  );

  return (
    <article className="keyframe-card">
      <FrameThumbnail
        frame={{ ...frame, jobId: job.id }}
        onSeek={onSeek}
      />

      <div className="keyframe-body">
        <FrameHeader
          index={offset + index + 1}
          scene={scene}
        />

        <FrameSummary
          road={road}
          objects={objects}
          text={texts[0]}
        />

        <details>
          <summary style={{ cursor: "pointer" }}>
            Подробности кадра
          </summary>

          <FrameObjects objects={objects} />

          <FramePlace frame={frame} />

          <FrameRoad road={road} />

          <FrameTexts texts={texts} />

          <FrameSpeech
            hasSpeech={speech.length > 0}
            nearby={nearby}
            shown={shownSpeech}
            onSeek={onSeek}
          />
        </details>
      </div>
    </article>
  );
}