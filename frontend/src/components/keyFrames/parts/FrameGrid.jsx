import { formatTime } from "../../../utils/formatTime.js";

function frameUrl(jobId, artifact) {
  return `/api/jobs/${jobId}/files/${artifact}`;
}

function hasText(frame, ocr) {
  return ocr.some(
    (item) =>
      Number(item.start) >= Number(frame.timestamp) &&
      Number(item.start) <= Number(frame.timestamp) + 0.5,
  );
}

function hasSpeech(frame, speech) {
  return speech.some(
    (item) =>
      Number(item.start) >= Number(frame.timestamp) - 2 &&
      Number(item.start) <= Number(frame.timestamp) + 2,
  );
}

// "дневной свет" → "день", "ночь или сильное затемнение" → "ночь" и т.п.
function lightingLabel(descriptor) {
  const value = String(descriptor?.lighting || "").toLowerCase();

  if (!value) return null;
  if (value.includes("ночь") || value.includes("затемн")) return "ночь";
  if (value.includes("сумер") || value.includes("пасмурн")) return "сумерки";
  if (value.includes("дневн")) return "день";
  return null;
}

// Топ-объект кадра по площади + остальные для «+N»
function topObject(frame) {
  const list = [...(frame.objects || [])].sort(
    (a, b) => Number(b.area_percent || 0) - Number(a.area_percent || 0),
  );
  if (!list.length) return null;
  const label = list[0].label_ru || list[0].label;
  const rest = list.length - 1;
  return rest > 0 ? `${label} +${rest}` : label;
}

function buildBadges(frame, ocr, speech) {
  const badges = [];

  const object = topObject(frame);
  if (object) badges.push(object);

  const lighting = lightingLabel(frame.descriptors);
  if (lighting) badges.push(lighting);

  if (hasText(frame, ocr)) badges.push("текст");
  if (hasSpeech(frame, speech)) badges.push("речь");

  return badges.slice(0, 3);
}

export default function FrameGrid({
  job,
  frames,
  offset,
  ocr,
  speech,
  onOpen,
}) {
  if (!frames.length) return null;

  return (
    <div className="frame-grid">
      {frames.map((frame, index) => {
        const badges = buildBadges(frame, ocr, speech);
        const url = frameUrl(job.id, frame.artifact);

        return (
          <button
            key={`${frame.artifact}-${frame.timestamp}-${index}`}
            type="button"
            className="frame-grid__card"
            onClick={() => onOpen(frame, offset + index)}
            title={`${formatTime(frame.timestamp)} · ${frame.artifact}`}
          >
            <img
              className="frame-grid__img"
              src={url}
              alt=""
              loading="lazy"
              decoding="async"
            />

            <span className="frame-grid__time">
              {formatTime(frame.timestamp)}
            </span>

            {badges.length > 0 && (
              <span className="frame-grid__badges">
                {badges.map((label) => (
                  <span key={label} className="frame-grid__badge">
                    {label}
                  </span>
                ))}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}