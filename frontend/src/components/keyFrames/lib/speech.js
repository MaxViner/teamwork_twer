import {
  SPEECH_LIMIT,
  SPEECH_WINDOW_SECONDS,
} from "./constants.js";

export function speechSegments(job) {
  const observations = job?.stages?.speech?.observations || [];

  const segments = [];

  for (const observation of observations) {
    const stored = observation?.data?.segments;

    if (Array.isArray(stored) && stored.length) {
      for (const segment of stored) {
        segments.push({
          start: Number(segment.start),
          end: Number(segment.end ?? segment.start),
          text: segment.text || "",
        });
      }

      continue;
    }

    if (observation.source === "speech") {
      segments.push({
        start: Number(observation.start),
        end: Number(observation.end ?? observation.start),
        text: observation.corrected_text ?? observation.text ?? "",
      });
    }
  }

  return segments
    .filter((segment) => Number.isFinite(segment.start))
    .sort((a, b) => a.start - b.start);
}

export function nearbySpeech(segments, timestamp) {
  const from = timestamp - SPEECH_WINDOW_SECONDS;
  const to = timestamp + SPEECH_WINDOW_SECONDS;

  return segments.filter(
    (segment) => segment.end >= from && segment.start <= to,
  );
}

export function speechDistance(segment, timestamp) {
  if (timestamp < segment.start) {
    return segment.start - timestamp;
  }

  if (timestamp > segment.end) {
    return timestamp - segment.end;
  }

  return 0;
}

export function closestSpeech(segments, timestamp) {
  return [...segments]
    .sort(
      (a, b) => (
        speechDistance(a, timestamp)
        - speechDistance(b, timestamp)
      ),
    )
    .slice(0, SPEECH_LIMIT)
    .sort((a, b) => a.start - b.start);
}