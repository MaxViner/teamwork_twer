import { formatPercent } from "../lib/format.js";

export default function FrameObjects({ objects }) {
  if (!objects.length) {
    return (
      <div className="keyframe-row">
        <span className="keyframe-label">Объекты</span>

        <span className="muted">не найдены</span>
      </div>
    );
  }

  return (
    <div className="keyframe-row">
      <span className="keyframe-label">Объекты</span>

      <div className="keyframe-chips">
        {objects.slice(0, 6).map((item, index) => (
          <span
            className="keyframe-chip"
            key={`${item.label}-${index}`}
            title={Number.isFinite(Number(item.confidence))
              ? `Уверенность ${Math.round(Number(item.confidence) * 100)}%`
              : undefined}
          >
            {item.label_ru || item.label}

            {formatPercent(item.area_percent) && (
              ` · ${formatPercent(item.area_percent)}`
            )}
          </span>
        ))}

        {objects.length > 6 && (
          <span className="muted">
            +{objects.length - 6}
          </span>
        )}
      </div>
    </div>
  );
}