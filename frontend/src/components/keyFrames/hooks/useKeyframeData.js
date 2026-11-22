// hooks/useKeyframeData.js
import { useMemo } from "react";
import { buildFrames } from "../lib/frames.js";
import { roadSegments } from "../lib/roads.js";
import { ocrObservations } from "../lib/ocr.js";
import { speechSegments } from "../lib/speech.js";

export function useKeyframeData(job) {
  const roads = useMemo(
    () => roadSegments(job),
    [job],
  );

  const frames = useMemo(
    () => buildFrames(job, roads),
    [job, roads],
  );

  const ocr = useMemo(
    () => ocrObservations(job),
    [job],
  );

  const speech = useMemo(
    () => speechSegments(job),
    [job],
  );

  const scenes = job?.stages?.scenes?.result?.intervals || [];

  return {
    roads,
    frames,
    ocr,
    speech,
    scenes,
  };
}