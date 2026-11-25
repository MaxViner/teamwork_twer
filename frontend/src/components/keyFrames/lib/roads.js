import {
  ROAD_MATCH_TOLERANCE_SECONDS,
  ROAD_SEMANTIC_LABELS,
  ROAD_SEMANTIC_MIN_PERCENT,
} from "./constants.js";
import { roundTime } from "./format.js";

export function roadSegments(job) {
  const place = job?.stages?.place_profile;
  const stage = place || job?.stages?.road_geometry;
  const observations = stage?.observations || [];
  const road = place?.result?.road || job?.stages?.road_geometry?.result;

  const segments = [];

  for (const observation of observations) {
    if (observation.review === "rejected") {
      continue;
    }

    const stored = observation?.data?.segments;

    if (Array.isArray(stored) && stored.length) {
      for (const segment of stored) {
        segments.push({
          ...segment,
          artifact: segment.artifact || observation.artifact,
        });
      }

      continue;
    }

    if (
      observation.source !== "road_geometry"
      && observation.source !== "place_profile"
    ) {
      continue;
    }

    segments.push({
      start: observation.start,
      end: observation.end,
      text: observation.corrected_text ?? observation.text,
      artifact: observation.artifact,
      confidence: observation.data?.confidence,
      semantic_road_percent: observation.data?.semantic_road_percent,
    });
  }

  if (road?.episode_schema_version === 1) {
    return segments;
  }

  const semantic = semanticRoadFrames(job);

  return segments.filter(
    (segment) => roadAllowedByMask(semantic, Number(segment.start)),
  );
}

export function semanticRoadFrames(job) {
  const result = job?.stages?.visual_analysis?.result
    || job?.stages?.scene_objects?.result;

  if (
    result?.method
    && result.method !== "segformer"
  ) {
    return null;
  }

  const frames = result?.frames;

  if (!Array.isArray(frames) || !frames.length) {
    return null;
  }

  const evidence = new Map();

  for (const frame of frames) {
    const timestamp = Number(frame?.timestamp);

    if (!Number.isFinite(timestamp)) {
      continue;
    }

    let percent = 0;

    for (const item of frame.objects || []) {
      if (ROAD_SEMANTIC_LABELS.includes(item?.label)) {
        percent += Number(item.area_percent) || 0;
      }
    }

    evidence.set(roundTime(timestamp), percent);
  }

  return evidence.size ? evidence : null;
}

export function roadAllowedByMask(evidence, timestamp) {
  if (!evidence || !Number.isFinite(timestamp)) {
    return true;
  }

  let nearestKey = null;
  let nearestDiff = Infinity;

  for (const key of evidence.keys()) {
    const diff = Math.abs(key - timestamp);

    if (diff < nearestDiff) {
      nearestKey = key;
      nearestDiff = diff;
    }
  }

  if (
    nearestKey === null
    || nearestDiff > ROAD_MATCH_TOLERANCE_SECONDS
  ) {
    return false;
  }

  return evidence.get(nearestKey) >= ROAD_SEMANTIC_MIN_PERCENT;
}