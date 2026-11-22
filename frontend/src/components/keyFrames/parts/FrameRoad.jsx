import { cleanRoadText } from "../lib/format.js";

export default function FrameRoad({ road }) {
  return (
    <div className="keyframe-row">
      <span className="keyframe-label">Дорога</span>

      {road ? (
        <div className="keyframe-text">
          <p>{cleanRoadText(road.text)}</p>

          {(road.semantic_road_percent != null
            || road.confidence != null) && (
            <p className="keyframe-metrics">
              {road.semantic_road_percent != null && (
                `маска дороги ${road.semantic_road_percent}%`
              )}

              {road.semantic_road_percent != null
                && road.confidence != null && (
                " · "
              )}

              {road.confidence != null && (
                `уверенность ${Math.round(Number(road.confidence) * 100)}%`
              )}
            </p>
          )}
        </div>
      ) : (
        <span className="muted">признаков не найдено</span>
      )}
    </div>
  );
}