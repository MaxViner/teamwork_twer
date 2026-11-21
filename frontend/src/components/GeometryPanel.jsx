import { useEffect, useMemo, useState } from "react";
import { fileUrl } from "../utils/fileUrl.js";
import { formatTime } from "../utils/formatTime.js";


const FRAMES_PER_PAGE = 12;


function landmarksResult(job) {
    return job?.stages?.landmarks?.result || {};
}


function geometryFacts(geometry) {
    const facts = [];

    if (geometry?.median_horizon !== null && geometry?.median_horizon !== undefined) {
        facts.push(
            `горизонт ≈ ${Math.round(Number(geometry.median_horizon) * 100)}% высоты`,
        );
    }

    if (geometry?.median_vanishing_x !== null && geometry?.median_vanishing_x !== undefined) {
        const x = Number(geometry.median_vanishing_x);
        const side = x < 0.42 ? "слева" : x > 0.58 ? "справа" : "по центру";

        facts.push(`точка схода ${side} (${Math.round(x * 100)}% ширины)`);
    }

    const vertical = geometry?.vertical_profile;

    if (vertical && typeof vertical === "object") {
        const parts = Object.entries(vertical)
            .map(([name, count]) => `${name} — ${count}`);

        if (parts.length) {
            facts.push(`вертикали: ${parts.join(", ")}`);
        }
    }

    if (geometry?.median_symmetry !== null && geometry?.median_symmetry !== undefined) {
        facts.push(
            `симметрия ${Math.round(Number(geometry.median_symmetry) * 100)}%`,
        );
    }

    if (
        geometry?.median_skyline_roughness !== null
        && geometry?.median_skyline_roughness !== undefined
    ) {
        const value = Number(geometry.median_skyline_roughness);

        facts.push(
            value >= 0.16
                ? "силуэт застройки рваный"
                : "силуэт застройки ровный",
        );
    }

    if (geometry?.vanishing_frames) {
        facts.push(`точка схода найдена на ${geometry.vanishing_frames} кадрах`);
    }

    return facts;
}


export default function GeometryPanel({ job, onSeek }) {
    const result = landmarksResult(job);
    const landmarks = Array.isArray(result.landmarks) ? result.landmarks : [];
    const frames = Array.isArray(result.frames) ? result.frames : [];

    const [page, setPage] = useState(1);

    useEffect(() => {
        setPage(1);
    }, [job?.id]);

    const ordered = useMemo(() => {
        const score = (frame) => (
            (Array.isArray(frame.signs) ? frame.signs.length : 0) * 2
            + (Array.isArray(frame.landmarks) ? frame.landmarks.length : 0) * 3
        );

        return [...frames].sort(
            (a, b) => score(b) - score(a) || a.timestamp - b.timestamp,
        );
    }, [frames]);

    if (!result || (!landmarks.length && !frames.length)) {
        return null;
    }

    const facts = geometryFacts(result.geometry);
    const pages = Math.max(1, Math.ceil(ordered.length / FRAMES_PER_PAGE));
    const current = Math.min(page, pages);
    const visible = ordered.slice(
        (current - 1) * FRAMES_PER_PAGE,
        current * FRAMES_PER_PAGE,
    );

    return (
        <section className="panel geometry-panel">
            <div className="section-row">
                <div>
                    <h2>Ориентиры и геометрия кадров</h2>
                    <p className="muted">
                        Признаки для сопоставления с картой и снимками:
                        ориентиры, линия горизонта, точка схода и силуэт
                        застройки. Это не координаты.
                    </p>
                </div>

                <span className="insight-count">
                    {result.frame_count_total || frames.length} кадр.
                </span>
            </div>

            {landmarks.length > 0 && (
                <div className="geometry-landmarks">
                    {landmarks.slice(0, 12).map((item) => (
                        <div className="geometry-landmark" key={item.label}>
                            <strong>{item.label}</strong>
                            <span>
                                {item.frame_count} кадр.
                                {" · "}
                                до {item.max_area_percent}%
                            </span>

                            {Array.isArray(item.timestamps) && item.timestamps.length > 0 && (
                                <div className="geometry-landmark-times">
                                    {item.timestamps.slice(0, 4).map((moment) => (
                                        <button
                                            className="insight-time"
                                            key={moment}
                                            onClick={() => onSeek(moment)}
                                        >
                                            {formatTime(moment)}
                                        </button>
                                    ))}
                                </div>
                            )}
                        </div>
                    ))}
                </div>
            )}

            {facts.length > 0 && (
                <div className="insight-block">
                    <h3>Геометрия</h3>

                    <ul className="geometry-facts">
                        {facts.map((value) => (
                            <li key={value}>{value}</li>
                        ))}
                    </ul>
                </div>
            )}

            {visible.length > 0 && (
                <div className="geometry-frames">
                    {visible.map((frame) => (
                        <button
                            className="geometry-frame"
                            key={frame.timestamp}
                            onClick={() => onSeek(frame.timestamp)}
                            title={frame.geometry_text || formatTime(frame.timestamp)}
                        >
                            <span className="geometry-frame-media">
                                <img
                                    src={fileUrl(job.id, frame.artifact)}
                                    alt={`Кадр ${formatTime(frame.timestamp)}`}
                                    loading="lazy"
                                />

                                <span className="kf-frame-time">
                                    {formatTime(frame.timestamp)}
                                </span>
                            </span>

                            <span className="geometry-frame-text">
                                {frame.geometry_text
                                    || "Геометрия не оценена"}

                                {Array.isArray(frame.landmarks) && frame.landmarks.length > 0 && (
                                    <em>
                                        {" "}Видно: {frame.landmarks
                                            .map((item) => item.label_ru || item.label)
                                            .filter(Boolean)
                                            .slice(0, 3)
                                            .join(", ")}.
                                    </em>
                                )}

                                {Array.isArray(frame.signs) && frame.signs.length > 0 && (
                                    <em>
                                        {" "}Надписи: {frame.signs.slice(0, 2).join("; ")}.
                                    </em>
                                )}
                            </span>
                        </button>
                    ))}
                </div>
            )}

            {pages > 1 && (
                <div className="insight-pager">
                    <button
                        className="insight-page-button"
                        disabled={current <= 1}
                        onClick={() => setPage(current - 1)}
                    >
                        ←
                    </button>

                    <span className="muted">
                        Кадры: {current} / {pages}
                    </span>

                    <button
                        className="insight-page-button"
                        disabled={current >= pages}
                        onClick={() => setPage(current + 1)}
                    >
                        →
                    </button>
                </div>
            )}
        </section>
    );
}
