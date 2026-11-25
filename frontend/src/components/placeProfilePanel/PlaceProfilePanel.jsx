import { useEffect, useState } from "react";
import { fileUrl } from "../../utils/fileUrl.js";
import { formatTime } from "../../utils/formatTime.js";


const TABS = [
    { id: "road", label: "Дорога" },
    { id: "geometry", label: "Геометрия" },
    { id: "landmarks", label: "Ориентиры" },
    { id: "odometry", label: "Одометрия" },
    { id: "bev", label: "BEV" },
];


function resultOf(job) {
    return job?.stages?.place_profile?.result || {};
}


function RoadTab({ result }) {
    const road = result.road || {};
    const summary = road.summary || {};
    const episodes = Array.isArray(road.episodes) ? road.episodes : [];
    const schematic = road.schematic || {};

    return (
        <>
            <div className="insight-block">
                <h3>Сводка</h3>

                <dl className="profile-grid">
                    <div>
                        <dt>Дорога найдена</dt>
                        <dd>{summary.road_detected ? "да" : "нет"}</dd>
                    </div>
                    <div>
                        <dt>Направление</dt>
                        <dd>{summary.direction || "—"}</dd>
                    </div>
                    <div>
                        <dt>Кадров с дорогой</dt>
                        <dd>
                            {summary.detected_frames ?? 0} из{" "}
                            {summary.sampled_frames ?? 0}
                        </dd>
                    </div>
                    <div>
                        <dt>Уверенность</dt>
                        <dd>{summary.confidence ?? "—"}</dd>
                    </div>
                </dl>
            </div>

            {episodes.length > 0 && (
                <div className="insight-block">
                    <h3>Эпизоды</h3>

                    <div className="clue-cards">
                        {episodes.map((episode) => (
                            <article className="clue-card" key={episode.id}>
                                <strong>{episode.bend_label || "Дорога"}</strong>
                                <span>
                                    {formatTime(episode.start)} —{" "}
                                    {formatTime(episode.end)}
                                </span>
                                <small>{episode.frame_count} кадр.</small>
                            </article>
                        ))}
                    </div>
                </div>
            )}

            {schematic.sequence && (
                <div className="insight-block">
                    <h3>Схема</h3>
                    <p>{schematic.sequence}</p>
                    {schematic.note && (
                        <p className="muted">{schematic.note}</p>
                    )}
                </div>
            )}
        </>
    );
}


function GeometryTab({ result }) {
    const geometry = result.geometry || {};
    const frames = Array.isArray(result.geometry_frames)
        ? result.geometry_frames
        : [];

    return (
        <>
            <div className="insight-block">
                <h3>Сводка геометрии</h3>

                <dl className="profile-grid">
                    <div>
                        <dt>Кадров</dt>
                        <dd>{geometry.frame_count ?? result.geometry_frame_count ?? 0}</dd>
                    </div>
                    <div>
                        <dt>Медианный горизонт</dt>
                        <dd>
                            {geometry.median_horizon != null
                                ? `${Math.round(geometry.median_horizon * 100)}%`
                                : "—"}
                        </dd>
                    </div>
                    <div>
                        <dt>Точка схода по X</dt>
                        <dd>
                            {geometry.median_vanishing_x != null
                                ? `${Math.round(geometry.median_vanishing_x * 100)}%`
                                : "—"}
                        </dd>
                    </div>
                    <div>
                        <dt>Симметрия</dt>
                        <dd>{geometry.median_symmetry ?? "—"}</dd>
                    </div>
                </dl>
            </div>

            {frames.length > 0 && (
                <div className="insight-block">
                    <h3>Кадры</h3>

                    <div className="clue-cards">
                        {frames.slice(0, 24).map((frame) => (
                            <article
                                className="clue-card"
                                key={`${frame.timestamp}-${frame.artifact}`}
                            >
                                <strong>{formatTime(frame.timestamp)}</strong>
                                <span>{frame.geometry_text || "—"}</span>
                            </article>
                        ))}
                    </div>
                </div>
            )}
        </>
    );
}


function LandmarksTab({ job, result, onSeek }) {
    const landmarks = Array.isArray(result.landmarks) ? result.landmarks : [];
    const frames = Array.isArray(result.geometry_frames)
        ? result.geometry_frames
        : [];

    if (!landmarks.length) {
        return <p className="muted">Узнаваемые ориентиры не найдены.</p>;
    }

    return (
        <>
            <div className="insight-block">
                <h3>Главные зацепки</h3>

                <div className="clue-cards">
                    {landmarks.map((item) => (
                        <button
                            type="button"
                            className="clue-card"
                            key={`${item.label}-${item.timestamps?.[0] || "none"}`}
                            onClick={() => onSeek(Number(item.timestamps?.[0]) || 0)}
                        >
                            <strong>{item.label}</strong>
                            <span>{item.frame_count} кадр.</span>
                            {Number.isFinite(Number(item.max_area_percent)) && (
                                <small>до {Number(item.max_area_percent).toFixed(1)}%</small>
                            )}
                        </button>
                    ))}
                </div>
            </div>

            {frames.length > 0 && (
                <div className="insight-block">
                    <h3>Кадры с ориентирами</h3>

                    <div className="clue-cards">
                        {frames
                            .filter((frame) => frame.landmarks?.length && frame.artifact)
                            .slice(0, 12)
                            .map((frame) => (
                                <button
                                    type="button"
                                    className="clue-card clue-card--image"
                                    key={`${frame.timestamp}-${frame.artifact}`}
                                    onClick={() => onSeek(frame.timestamp)}
                                >
                                    <img
                                        src={fileUrl(job.id, frame.artifact)}
                                        alt="Кадр с ориентиром"
                                        loading="lazy"
                                    />
                                    <span>
                                        {frame.landmarks
                                            .map((item) => item.label_ru || item.label)
                                            .join(", ")}
                                    </span>
                                </button>
                            ))}
                    </div>
                </div>
            )}
        </>
    );
}


function OdometryTab({ result }) {
    const odometry = result.odometry || {};
    const trajectory = odometry.trajectory || {};
    const scale = odometry.scale || {};
    const skipped = Array.isArray(odometry.skipped) ? odometry.skipped : [];

    return (
        <>
            <div className="insight-block">
                <h3>Движение камеры</h3>

                <dl className="profile-grid">
                    <div>
                        <dt>Успешных пар</dt>
                        <dd>{odometry.successful_pairs ?? 0}</dd>
                    </div>
                    <div>
                        <dt>Пропущено</dt>
                        <dd>{odometry.skipped_pairs ?? 0}</dd>
                    </div>
                    <div>
                        <dt>Точек траектории</dt>
                        <dd>{trajectory.points?.length ?? 0}</dd>
                    </div>
                    <div>
                        <dt>Масштаб</dt>
                        <dd>
                            {scale.source || "—"}
                            {scale.m_per_unit != null
                                ? ` · ×${scale.m_per_unit}`
                                : ""}
                        </dd>
                    </div>
                </dl>
            </div>

            {odometry.note && (
                <p className="muted">{odometry.note}</p>
            )}

            {skipped.length > 0 && (
                <div className="insight-block">
                    <h3>Пропущенные пары</h3>

                    <div className="clue-cards">
                        {skipped.slice(0, 12).map((item) => (
                            <article
                                className="clue-card"
                                key={`${item.from}-${item.to}`}
                            >
                                <strong>
                                    {formatTime(item.from_timestamp)} →{" "}
                                    {formatTime(item.to_timestamp)}
                                </strong>
                                <span>{item.reason}</span>
                            </article>
                        ))}
                    </div>
                </div>
            )}
        </>
    );
}


function BevTab({ job, result }) {
    const bev = result.bev;

    if (!bev) {
        return (
            <p className="muted">
                BEV не построена: нужно минимум три точки траектории.
            </p>
        );
    }

    return (
        <div className="insight-block">
            <h3>Топологическая карта</h3>

            <p className="muted">
                {bev.note || "Без метрики."}
                {bev.grid
                    ? ` Сетка ${bev.grid.rows}×${bev.grid.cols}, ячейка ${bev.grid.cell_size_m} м.`
                    : ""}
            </p>

            {bev.overlay_png && (
                <button
                    type="button"
                    className="bev-image"
                    onClick={() => window.open(fileUrl(job.id, bev.overlay_png), "_blank")}
                >
                    <img
                        src={fileUrl(job.id, bev.overlay_png)}
                        alt="Топологическая BEV-проекция"
                        loading="lazy"
                    />
                </button>
            )}

            <dl className="profile-grid">
                <div>
                    <dt>Объектов</dt>
                    <dd>{bev.objects?.length ?? 0}</dd>
                </div>
                <div>
                    <dt>Источник масштаба</dt>
                    <dd>{bev.scale_source || "—"}</dd>
                </div>
            </dl>
        </div>
    );
}


export default function PlaceProfilePanel({ job, onSeek }) {
    const [tab, setTab] = useState("road");
    const result = resultOf(job);

    useEffect(() => {
        setTab("road");
    }, [job?.id]);

    if (!job?.stages?.place_profile) {
        return null;
    }

    return (
        <section className="panel analysis-panel">
            <div className="section-row">
                <div>
                    <h2>Профиль места</h2>
                    <p className="muted">
                        Дорога, геометрия кадров, ориентиры, относительная
                        одометрия и топологическая BEV. Это признаки для
                        поиска, а не координаты.
                    </p>
                </div>
            </div>

            <div className="analysis-tabs" role="tablist">
                {TABS.map((item) => (
                    <button
                        key={item.id}
                        type="button"
                        role="tab"
                        aria-selected={tab === item.id}
                        className={`analysis-tab ${tab === item.id ? "is-active" : ""}`}
                        onClick={() => setTab(item.id)}
                    >
                        {item.label}
                    </button>
                ))}
            </div>

            <div className="analysis-tab-body">
                {tab === "road" && <RoadTab result={result} />}
                {tab === "geometry" && <GeometryTab result={result} />}
                {tab === "landmarks" && (
                    <LandmarksTab job={job} result={result} onSeek={onSeek} />
                )}
                {tab === "odometry" && <OdometryTab result={result} />}
                {tab === "bev" && <BevTab job={job} result={result} />}
            </div>
        </section>
    );
}
