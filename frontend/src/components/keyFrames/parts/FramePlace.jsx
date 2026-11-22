export default function FramePlace({ frame }) {
  const descriptors = frame.descriptors || {};
  const metrics = frame.metrics || {};

  const landscape = Array.isArray(descriptors.landscape)
    ? descriptors.landscape.join(", ")
    : "";

  const hasPlace = Boolean(
    descriptors.lighting
    || descriptors.weather
    || descriptors.season
    || landscape
    || Number.isFinite(Number(metrics.brightness)),
  );

  if (!hasPlace) {
    return null;
  }

  return (
    <div className="keyframe-row">
      <span className="keyframe-label">Место</span>

      <div className="keyframe-text">
        {(descriptors.lighting
          || descriptors.weather
          || descriptors.season) && (
          <p>
            {[
              descriptors.lighting,
              descriptors.weather,
              descriptors.season,
            ].filter(Boolean).join(" · ")}
          </p>
        )}

        {landscape && (
          <p className="muted">
            {landscape}
          </p>
        )}

        {Number.isFinite(Number(metrics.brightness)) && (
          <p className="keyframe-metrics">
            яркость {Math.round(Number(metrics.brightness))}
            {" · "}
            контраст {Math.round(Number(metrics.contrast))}
            {" · "}
            насыщенность {Math.round(Number(metrics.saturation))}
          </p>
        )}
      </div>
    </div>
  );
}