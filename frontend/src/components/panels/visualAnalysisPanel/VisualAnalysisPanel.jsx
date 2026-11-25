import { useEffect, useMemo, useState } from "react";
import { describeObject, fetchAiStatus } from "../../../api/jobs.js";
import { fileUrl } from "../../../utils/fileUrl.js";
import { formatTime } from "../../../utils/formatTime.js";
import AiDescription from "../../landmarksPanel/AiDescription.jsx";


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
    { id: "scenes", label: "Сцены" },
    { id: "ocr", label: "Текст" },
    { id: "detections", label: "YOLO-детекции" },
    { id: "segments", label: "Семантика" },
    { id: "faces", label: "Лица" },
];

const OCR_PER_PAGE = 60;


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


function ScenesTab({ job, onSeek }) {
    const stage = job?.stages?.scenes;
    const result = stage?.result || {};
    const intervals = Array.isArray(result.intervals) ? result.intervals : [];

    if (!intervals.length) {
        return (
            <p className="muted">
                {stage?.status === "skipped"
                    ? stage.error || "Поиск сцен пропущен."
                    : "Сцены не найдены."}
            </p>
        );
    }

    return (
        <div className="insight-block">
            <p className="muted">
                Найдено сцен: {result.scene_count ?? intervals.length}.
                Нажмите на время, чтобы перейти к началу сцены.
            </p>

            <ol className="transcript-list">
                {intervals.map(([start, end], index) => (
                    <li
                        className="transcript-row"
                        key={`${start}-${index}`}
                    >
                        <button
                            className="insight-time"
                            onClick={() => onSeek(start)}
                        >
                            {formatTime(start)}
                        </button>

                        <div className="transcript-text">
                            Сцена {index + 1}
                            {" · "}
                            {formatTime(start)} — {formatTime(end)}
                            <span className="muted">
                                {" "}({Math.max(0, Math.round(end - start))} с)
                            </span>
                        </div>
                    </li>
                ))}
            </ol>
        </div>
    );
}


function OcrTab({ job, onSeek }) {
    const stage = job?.stages?.ocr;
    const [page, setPage] = useState(1);

    const items = useMemo(() => {
        const list = stage?.observations;

        if (!Array.isArray(list)) {
            return [];
        }

        return list
            .filter((item) => item && item.text)
            .slice()
            .sort((a, b) => (Number(a.start) || 0) - (Number(b.start) || 0));
    }, [stage]);

    useEffect(() => {
        setPage(1);
    }, [job?.id]);

    if (!items.length) {
        const frameCount = stage?.result?.frames?.length ?? 0;

        return (
            <p className="muted">
                {stage?.status === "skipped"
                    ? stage.error || "Распознавание текста пропущено."
                    : frameCount > 0
                        ? `Проверено кадров: ${frameCount}. Читаемого текста не найдено.`
                        : "Текст на кадрах не найден."}
            </p>
        );
    }

    const pages = Math.max(1, Math.ceil(items.length / OCR_PER_PAGE));
    const current = Math.min(page, pages);
    const visible = items.slice(
        (current - 1) * OCR_PER_PAGE,
        current * OCR_PER_PAGE,
    );

    return (
        <div className="insight-block">
            <p className="muted">
                Распознано фрагментов: {items.length}.
                Нажмите на время, чтобы перейти к кадру.
            </p>

            <ol className="transcript-list">
                {visible.map((item, index) => (
                    <li
                        className="transcript-row"
                        key={item.id || `${item.start}-${index}`}
                    >
                        <button
                            className="insight-time"
                            onClick={() => onSeek(Number(item.start) || 0)}
                        >
                            {formatTime(Number(item.start) || 0)}
                        </button>

                        {item.artifact ? (
                            <button
                                className="landmark-thumb ocr-thumb"
                                onClick={() => onSeek(Number(item.start) || 0)}
                                title="Перейти к кадру"
                            >
                                <img
                                    src={fileUrl(job.id, item.artifact)}
                                    alt={item.text}
                                    loading="lazy"
                                />
                            </button>
                        ) : null}

                        <div className="transcript-text">
                            {item.text}

                            {Number.isFinite(Number(item.recognition_score)) && (
                                <span className="muted">
                                    {" "}· {Math.round(Number(item.recognition_score) * 100)}%
                                </span>
                            )}
                        </div>
                    </li>
                ))}
            </ol>

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
                        {current} / {pages}
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
        </div>
    );
}


export default function VisualAnalysisPanel({ job, onSeek }) {
    const hasVisual = Boolean(job?.stages?.visual_analysis);
    const hasScenes = Boolean(job?.stages?.scenes);
    const hasOcr = Boolean(job?.stages?.ocr);

    const defaultTab = hasVisual
        ? "objects"
        : hasScenes
            ? "scenes"
            : "ocr";

    const [tab, setTab] = useState(defaultTab);

    useEffect(() => {
        setTab(defaultTab);
    }, [job?.id, defaultTab]);

    if (!hasVisual && !hasScenes && !hasOcr) {
        return null;
    }

    const result = resultOf(job);
    const counts = result.counts || {};

    const sceneCount = job?.stages?.scenes?.result?.scene_count ?? 0;
    const textCount = job?.stages?.ocr?.observations?.length ?? 0;
    const frameCount = counts.frames ?? result.successful_frames ?? 0;

    const summary = [];
    if (sceneCount > 0) summary.push(`${sceneCount} сцен`);
    if (textCount > 0) summary.push(`${textCount} текстов`);
    if (frameCount > 0) summary.push(`${frameCount} кадр.`);

    return (
        <section className="panel analysis-panel">
            <div className="section-row">
                <div>
                    <h2>Визуальный анализ</h2>
                    <p className="muted">
                        Сцены, текст на кадрах, семантическая разметка,
                        YOLOv8n и анонимные лица. Это визуальные улики,
                        а не подтверждённые координаты.
                    </p>
                </div>

                {summary.length > 0 && (
                    <span className="insight-count">
                        {summary.join(" · ")}
                    </span>
                )}
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

                {tab === "scenes" && (
                    <ScenesTab job={job} onSeek={onSeek} />
                )}

                {tab === "ocr" && (
                    <OcrTab job={job} onSeek={onSeek} />
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
