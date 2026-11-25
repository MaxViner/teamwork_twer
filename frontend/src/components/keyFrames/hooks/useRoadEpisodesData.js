import { useMemo } from "react";

export function useRoadEpisodesData(job) {
  const place = job?.stages?.place_profile;
  const roadStage = place || job?.stages?.road_geometry;
  const road = place?.result?.road || roadStage?.result;

  const roadRejected = roadStage?.observations?.some((item) => (
    item.review === "rejected"
    && item.data?.kind === "road_geometry_summary"
  ));

  const episodes = useMemo(
    () => (roadRejected ? [] : road?.episodes || []),
    [roadRejected, road?.episodes],
  );

  return episodes;
}