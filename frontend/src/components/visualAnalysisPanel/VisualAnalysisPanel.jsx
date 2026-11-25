import { useEffect, useState } from "react";
import { describeObject, fetchAiStatus } from "../../api/jobs.js";
import { fileUrl } from "../../utils/fileUrl.js";
import { formatTime } from "../../utils/formatTime.js";
import AiDescription from "../landmarksPanel/AiDescription.jsx";


const CATEGORY_ORDER = [
    "architecture",
    "transport",
    "nature",
    "street",
    "other",
];


const CATEGORY_LABELS = {
    architecture: "Архитектура и ориентиры",
    transport: "Транспорт и дороги",
    nature: "Природа",
    street: "Уличные объекты",
    other: "Другие объекты",
};


const TABS = [
    { id: "objects", label: "Объекты" },
    { id: "detections", label: "YOLO-детекции" },
    { id: "segments", label: "Семантика" },
    { id: "faces", label: "Лица" },
];


function resultOf(job) {
    return job?.stages?.visual_analysis?.result || {};
}


function uniqueObjects(result) {
    if (Array.isArray(result.unique_objects) && result.unique_objects.length) {
        return result.unique_objects.map((item) => ({
            ...item,
            category: item.category || "other",
            timestamps: Array.isArray(item.timestamps) ? item.timestamps : [],
        }));
    }

    return [];
}


function groupsOf(objects) {
    return CATEGORY_ORDER
        .map((category) => ({
            category,
            items: objects.filter((item) => (item.category || "other") === category),
        }))
        .filter((group) => group.items.length > 0);
}


function TimeChips({ timestamps, onSeek, limit = 8 }) {
    if (!timestamps?.length) {
        return null;
    }

    return (
        <div className="landmark-times">
            {timestamps.slice(0, limit).map((timestamp) => (
                <button
                    className="interval-chip"
                    key={timestamp}
                    onClick={() => onSeek(timestamp)}
                >
                    {formatTime(timestamp)}
                </button>
            ))}

            {timestamps.length > limit && (
                <span className="muted">+{timestamps.length - limit}</span>
            )}
        </div>
    );
}


function ObjectsTab({ job, result, onSeek }) {
    const objects = uniqueObjects(result);
    const [aiStatus, setAiStatus] = useState(null);
    const [aiState, setAiState] = useState({});

    useEffect(() => {
        let active = true;

        fetchAiStatus()
            .then((status) => {
                if (active) {
                    setAiStatus(status);
                }
            })
            .catch(() => {
                if (active) {
                    setAiStatus({ configured: false, message: "" });
                }
            });

        return () => {
            active = false;
        };
    }, []);

    useEffect(() => {
        setAiState({});
    }, [job?.id]);

    const requestDescription = async (label, refresh) => {
        setAiState((current) => ({
            ...current,
            [label]: { loading: true, error: "" },
        }));

        try {
            const payload = await describeObject(job.id, label, { refresh });

            setAiState((current) => ({
                ...current,
                [label]: {
                    loading: false,
                    error: "",
                    description: payload.description,
                },
            }));
        } catch (error) {
            setAiState((current) => ({
                ...current,
                [label]: {
                    loading: false,
                    error: error.message,
                },
            }));
        }
    };

    if (!objects.length) {
        return <p className="muted">Семантические объекты не найдены.</p>;
    }

    return (
        <div className="landmark-groups">
            {groupsOf(objects).map((group) => (
                <section className="landmark-group" key={group.category}>
                    <h3>{CATEGORY_LABELS[group.category]}</h3>

                    <div className="landmark-list">
                        {group.items.map((item) => {
                            const timestamps = item.timestamps || [];

                            return (
                                <article className="landmark-card" key={item.label}>
                                    {item.best_frame && (
                                        <button
                                            className="landmark-thumb"
                                            onClick={() => onSeek(
                                                item.best_timestamp
                                                ?? timestamps[0]
                                                ?? 0,
                                            )}
                                            title="Перейти к лучшему кадру"
                                        >
                                            <img
                                                src={fileUrl(job.id, item.best_frame)}
                                                alt={item.label_ru || item.label}
                                                loading="lazy"
                                            />
                                        </button>
                                    )}

                                    <div className="landmark-body">
                                        <div className="landmark-title">
                                            <strong>{item.label_ru || item.label}</strong>
                                            <span className="landmark-count">
                                                {item.frame_count ?? timestamps.length} кадр.
                                            </span>
                                        </div>

                                        <p className="muted">
                                            до {item.max_area_percent ?? 0}% кадра
                                            {Number.isFinite(Number(item.mean_confidence))
                                                ? ` · уверенность ${Math.round(Number(item.mean_confidence) * 100)}%`
                                                : ""}
                                        </p>

                                        <TimeChips
                                            timestamps={timestamps}
                                            onSeek={onSeek}
                                        />

                                        <AiDescription
                                            description={
                                                aiState[item.label]?.description
                                                ?? item.ai_description
                                            }
                                            loading={aiState[item.label]?.loading}
                                            error={aiState[item.label]?.error}
                                            configured={aiStatus?.configured}
                                            hint={aiStatus?.message}
                                            onRequest={(refresh) => requestDescription(
                                                item.label,
                                                refresh,
                                            )}
                                        />
                                    </div>
                                </article>
                            );
                        })}
                    </div>
                </section>
            ))}
        </div>
    );
}


function DetectionsTab({ job, result, onSeek }) {
    const items = Array.isArray(result.unique_detections)
        ? result.unique_detections
        : [];

    if (!items.length) {
        return (
            <p className="muted">
                {result.detector_available === false
                    ? `YOLO недоступен: ${result.detector_error || "модель не загружена"}.`
                    : "Детекции не найдены."}
            </p>
        );
    }

    return (
        <div className="landmark-groups">
            <div className="landmark-list">
                {items.map((item) => {
                    const timestamps = Array.isArray(item.timestamps)
                        ? item.timestamps
                        : [];

                    return (
                        <article className="landmark-card" key={item.label}>
                            {item.best_frame && (
                                <button
                                    className="landmark-thumb"
                                    onClick={() => onSeek(
                                        item.best_timestamp
                                        ?? timestamps[0]
                                        ?? 0,
                                    )}
                                    title="Перейти к лучшему кадру"
                                >
                                    <img
                                        src={fileUrl(job.id, item.best_frame)}
                                        alt={item.label}
                                        loading="lazy"
                                    />
                                </button>
                            )}

                            <div className="landmark-body">
                                <div className="landmark-title">
                                    <strong>{item.label_ru || item.label}</strong>
                                    <span className="landmark-count">
                                        {item.frame_count ?? timestamps.length} кадр.
                                    </span>
                                </div>

                                <p className="muted">
                                    YOLOv8n · уверенность{" "}
                                    {Math.round(Number(item.mean_confidence || 0) * 100)}%
                                    {item.is_dynamic ? " · динамический объект" : ""}
                                </p>

                                <TimeChips
                                    timestamps={timestamps}
                                    onSeek={onSeek}
                                />
                            </div>
                        </article>
                    );
                })}
            </div>
        </div>
    );
}


function SegmentsTab({ result }) {
    const profile = result.profile || {};
    const landscape = Array.isArray(profile.landscape)
        ? profile.landscape.join(", ")
        : "";

    return (
        <div className="insight-block">
            <h3>Визуальный профиль</h3>

            <p className="muted">
                Метод разметки: {result.method || "нет данных"}
                {result.model ? ` · ${result.model}` : ""}.
                {result.segmentation_error
                    ? ` Ошибка модели: ${result.segmentation_error}`
                    : ""}
            </p>

            <dl className="profile-grid">
                <div>
                    <dt>Освещение</dt>
                    <dd>{profile.lighting || "—"}</dd>
                </div>
                <div>
                    <dt>Погода</dt>
                    <dd>{profile.weather || "—"}</dd>
                </div>
                <div>
                    <dt>Сезон</dt>
                    <dd>{profile.season || "—"}</dd>
                </div>
                <div>
                    <dt>Ландшафт</dt>
                    <dd>{landscape || "—"}</dd>
                </div>
                <div>
                    <dt>Кадров</dt>
                    <dd>
                        {result.successful_frames ?? 0} из{" "}
                        {result.sampled_frames ?? 0}
                    </dd>
                </div>
                <div>
                    <dt>Сегментов</dt>
                    <dd>{result.segment_count ?? 0}</dd>
                </div>
            </dl>
        </div>
    );
}


function FacesTab({ job, result, onSeek }) {
    const people = Array.isArray(result.people) ? result.people : [];

    if (!people.length) {
        return (
            <p className="muted">
                {result.face_available === false
                    ? "Модель лиц недоступна."
                    : "Лица не найдены."}
            </p>
        );
    }

    return (
        <div className="faces-grid">
            {people.map((person) => {
                const best = person.best_frame || {};

                return (
                    <article className="faces-card" key={person.label}>
                        <button
                            className="faces-media"
                            onClick={() => onSeek(person.first_start)}
                            title="Перейти к первому появлению"
                        >
                            {best.artifact ? (
                                <img
                                    src={fileUrl(job.id, best.artifact)}
                                    alt={person.label || "Человек"}
                                    loading="lazy"
                                />
                            ) : (
                                <span className="faces-placeholder" />
                            )}

                            <span className="kf-frame-time">
                                {formatTime(best.timestamp ?? person.first_start)}
                            </span>
                        </button>

                        <div className="faces-body">
                            <strong>{person.label || "Человек"}</strong>
                            <span className="muted">
                                {person.frame_count || 0} кадр. · с{" "}
                                {formatTime(person.first_start)}
                            </span>

                            <TimeChips
                                timestamps={person.timestamps || []}
                                onSeek={onSeek}
                                limit={4}
                            />
                        </div>
                    </article>
                );
            })}
        </div>
    );
}


export default function VisualAnalysisPanel({ job, onSeek }) {
    const [tab, setTab] = useState("objects");
    const result = resultOf(job);

    useEffect(() => {
        setTab("objects");
    }, [job?.id]);

    if (!job?.stages?.visual_analysis) {
        return null;
    }

    const counts = result.counts || {};

    return (
        <section className="panel analysis-panel">
            <div className="section-row">
                <div>
                    <h2>Визуальный анализ</h2>
                    <p className="muted">
                        Один проход: метрики, семантическая разметка, YOLOv8n
                        и анонимные лица. Это визуальные улики, а не
                        подтверждённые координаты.
                    </p>
                </div>

                <span className="insight-count">
                    {counts.frames ?? result.successful_frames ?? 0} кадр.
                </span>
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
                {tab === "objects" && (
                    <ObjectsTab job={job} result={result} onSeek={onSeek} />
                )}

                {tab === "detections" && (
                    <DetectionsTab job={job} result={result} onSeek={onSeek} />
                )}

                {tab === "segments" && (
                    <SegmentsTab result={result} />
                )}

                {tab === "faces" && (
                    <FacesTab job={job} result={result} onSeek={onSeek} />
                )}
            </div>
        </section>
    );
}
