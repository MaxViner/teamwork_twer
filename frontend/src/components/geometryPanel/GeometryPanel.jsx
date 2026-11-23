import FrameGallery from "../ui/FrameGallery.jsx";
import { formatTime } from "../../utils/formatTime.js";

const LOW_VALUE = new Set([
    "tree",
    "trees",
    "grass",
    "sky",
    "earth",
    "plant",
    "wall",
]);

function resultOf(job) {
    return job?.stages?.landmarks?.result || {};
}

function meaningfulLandmarks(items) {
    return (Array.isArray(items) ? items : [])
        .filter((item) => item?.label && item?.frame_count)
        .filter((item) => !LOW_VALUE.has(String(item.label).toLowerCase()))
        .sort((a, b) => (
            Number(b.max_area_percent || 0) - Number(a.max_area_percent || 0)
            || Number(b.frame_count || 0) - Number(a.frame_count || 0)
        ));
}

function frameObjects(frame) {
    return (frame?.landmarks || [])
        .map((item) => item.label_ru || item.label)
        .filter(Boolean)
        .filter((label) => !LOW_VALUE.has(String(label).toLowerCase()));
}

export default function GeometryPanel({ job, onSeek }) {
    const result = resultOf(job);
    const landmarks = meaningfulLandmarks(result.landmarks);
    const frames = (Array.isArray(result.frames) ? result.frames : [])
        .map((frame) => ({ ...frame, objects: frameObjects(frame) }))
        .filter((frame) => frame.objects.length && frame.artifact)
        .map((frame) => ({
            artifact: frame.artifact,
            timestamp: frame.timestamp,
            caption: frame.objects.join(", "),
        }));

    if (!landmarks.length && !frames.length) return null;

    return (
        <section className="panel geometry-panel clue-panel">
            <div className="section-row">
                <div>
                    <h2>Ориентиры в кадрах</h2>
                    <p className="muted">
                        Только зацепки для сверки с картой, панорамами и фотографиями.
                        Техническая геометрия кадра скрыта, потому что сама по себе не помогает найти место.
                    </p>
                </div>
                {result.frame_count_total ? (
                    <span className="insight-count">{result.frame_count_total} кадр.</span>
                ) : null}
            </div>

            {landmarks.length > 0 && (
                <div className="insight-block">
                    <h3>Главные зацепки</h3>
                    <div className="clue-cards">
                        {landmarks.map((item) => (
                            <button
                                type="button"
                                className="clue-card"
                                key={`${item.label}-${item.timestamps?.[0] || "none"}`}
                                onClick={() => Number.isFinite(Number(item.timestamps?.[0])) && onSeek?.(Number(item.timestamps[0]))}
                            >
                                <strong>{item.label}</strong>
                                <span>{item.frame_count} кадр.</span>
                                {Number.isFinite(Number(item.max_area_percent)) ? (
                                    <small>до {Number(item.max_area_percent).toFixed(1)}%</small>
                                ) : null}
                                <span className="clue-card__times">
                                    {(item.timestamps || []).slice(0, 6).map((time) => (
                                        <span key={`${item.label}-${time}`}>{formatTime(time)}</span>
                                    ))}
                                </span>
                            </button>
                        ))}
                    </div>
                </div>
            )}

            {frames.length > 0 && (
                <div className="insight-block">
                    <h3>Опорные кадры</h3>
                    <FrameGallery
                        jobId={job.id}
                        frames={frames}
                        onSeek={onSeek}
                    />
                </div>
            )}
        </section>
    );
}
