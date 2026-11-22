import { roundTime } from "./format.js";

export function frameResult(job, stageId) {
  const frames = job?.stages?.[stageId]?.result?.frames;

  return Array.isArray(frames) ? frames : [];
}

export function buildFrames(job, roads) {
  const collected = new Map();

  const add = (frame) => {
    const timestamp = Number(frame?.timestamp);

    if (!Number.isFinite(timestamp)) {
      return;
    }

    const key = roundTime(timestamp);

    let entry = collected.get(key);

    if (!entry) {
      entry = {
        timestamp,
        artifact: null,
        objects: [],
        metrics: null,
        descriptors: null,
      };

      collected.set(key, entry);
    }

    if (!entry.artifact && frame.artifact) {
      entry.artifact = frame.artifact;
    }

    if (Array.isArray(frame.objects)) {
      entry.objects = frame.objects;
    }

    if (frame.metrics) {
      entry.metrics = frame.metrics;
    }

    if (frame.descriptors) {
      entry.descriptors = frame.descriptors;
    }
  };

  for (const frame of frameResult(job, "visual_profile")) {
    add(frame);
  }

  for (const frame of frameResult(job, "scene_objects")) {
    add(frame);
  }

  for (const frame of frameResult(job, "ocr")) {
    add(frame);
  }

  for (const road of roads) {
    if (road.artifact) {
      add({
        timestamp: road.start,
        artifact: road.artifact,
      });
    }
  }

  return [...collected.values()].sort(
    (a, b) => a.timestamp - b.timestamp,
  );
}