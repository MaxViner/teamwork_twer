import { roundTime } from "./format.js";

export function ocrObservations(job) {
  return (job?.stages?.ocr?.observations || []).filter(
    (item) => item.source === "ocr" && item.review !== "rejected",
  );
}

export function textsForFrame(observations, frame) {
  const texts = observations
    .filter((item) => (
      (frame.artifact && item.frame_artifact === frame.artifact)
      || roundTime(Number(item.start)) === roundTime(frame.timestamp)
    ))
    .map((item) => item.corrected_text ?? item.text)
    .filter(Boolean);

  return [...new Set(texts)];
}