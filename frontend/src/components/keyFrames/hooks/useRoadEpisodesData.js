import { useMemo } from "react";

export function useRoadEpisodesData(job) {
  const roadStage = job?.stages?.road_geometry;

  const roadRejected = roadStage?.observations?.some((item) => (
    item.review === "rejected"
    && item.data?.kind === "road_geometry_summary"
  ));

  const episodes = useMemo(
    () => (roadRejected ? [] : roadStage?.result?.episodes || []),
    [roadRejected, roadStage?.result?.episodes],
  );

  return episodes;
}