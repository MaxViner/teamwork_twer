import { fileUrl } from "../utils/fileUrl.js";
import { formatTime } from "../utils/formatTime.js";


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


const LABEL_CATEGORY = {
    building: "architecture",
    house: "architecture",
    tower: "architecture",
    skyscraper: "architecture",
    wall: "architecture",
    castle: "architecture",
    church: "architecture",
    temple: "architecture",
    monument: "architecture",
    column: "architecture",
    fountain: "architecture",
    bridge: "architecture",
    pier: "architecture",
    car: "transport",
    bus: "transport",
    truck: "transport",
    boat: "transport",
    road: "transport",
    path: "transport",
    tree: "nature",
    grass: "nature",
    plant: "nature",
    field: "nature",
    mountain: "nature",
    hill: "nature",
    rock: "nature",
    sand: "nature",
    water: "nature",
    river: "nature",
    lake: "nature",
    sea: "nature",
    earth: "nature",
    sky: "nature",
    snow: "nature",
    signboard: "street",
    streetlight: "street",
    pole: "street",
    fence: "street",
};


const CATEGORY_BY_LABEL_RU = {
    "водная поверхность": "nature",
    "растительность": "nature",
    "открытое небо": "nature",
    "дорога или асфальт, возможно": "transport",
    "скалы или плотная застройка, возможно": "architecture",
    "яркая светлая поверхность": "nature",
    "крупная ровная поверхность (вода, асфальт или снег)": "nature",
};


function categoryFor(label, labelRu) {
    return (
        LABEL_CATEGORY[label]
        || CATEGORY_BY_LABEL_RU[labelRu]
        || "other"
    );
}


function uniqueFromFrames(frames) {
    const collected = new Map();

    for (const frame of frames) {
        const timestamp = Number(frame?.timestamp);

        if (!Number.isFinite(timestamp)) {
            continue;
        }

        for (const item of frame.objects || []) {
            const label = item?.label;

            if (!label) {
                continue;
            }

            let entry = collected.get(label);

            if (!entry) {
                entry = {
                    label,
                    label_ru: item.label_ru || label,
                    category: categoryFor(label, item.label_ru || label),
                    frame_count: 0,
                    max_area_percent: 0,
                    mean_confidence: 0,
                    best_frame: null,
                    best_timestamp: null,
                    timestamps: [],
                    _confidence_sum: 0,
                };
                collected.set(label, entry);
            }

            const area = Number(item.area_percent) || 0;
            const confidence = Number(item.confidence) || 0;

            entry.frame_count += 1;
            entry._confidence_sum += confidence;
            entry.timestamps.push(timestamp);

            if (area > entry.max_area_percent) {
                entry.max_area_percent = area;
                entry.best_frame = frame.artifact || null;
                entry.best_timestamp = timestamp;
            }
        }
    }

    return [...collected.values()]
        .map((entry) => {
            const timestamps = [...new Set(entry.timestamps)].sort((a, b) => a - b);

            return {
                ...entry,
                frame_count: timestamps.length,
                max_area_percent: Math.round(entry.max_area_percent * 10) / 10,
                mean_confidence: Math.round(
                    (entry._confidence_sum / Math.max(entry.frame_count, 1)) * 1000,
                ) / 1000,
                timestamps,
                _confidence_sum: undefined,
            };
        })
        .sort((a, b) => {
            const rank = (category) => {
                const index = CATEGORY_ORDER.indexOf(category);
                return index === -1 ? CATEGORY_ORDER.length : index;
            };

            const categoryDiff = rank(a.category) - rank(b.category);

            return (
                categoryDiff
                || b.frame_count - a.frame_count
                || b.max_area_percent - a.max_area_percent
                || a.label_ru.localeCompare(b.label_ru)
            );
        });
}


function uniqueObjects(stage) {
    const result = stage?.result;
    const stored = result?.unique_objects;

    if (Array.isArray(stored) && stored.length) {
        return stored.map((item) => ({
            ...item,
            category: item.category || categoryFor(item.label, item.label_ru),
            timestamps: Array.isArray(item.timestamps)
                ? item.timestamps
                : [],
        }));
    }

    return uniqueFromFrames(result?.frames || []);
}


export default function LandmarksPanel({ job, onSeek }) {
    const stage = job?.stages?.scene_objects;

    if (!stage) {
        return null;
    }

    const objects = uniqueObjects(stage);

    if (!objects.length) {
        return null;
    }

    const groups = CATEGORY_ORDER
        .map((category) => ({
            category,
            items: objects.filter((item) => item.category === category),
        }))
        .filter((group) => group.items.length > 0);

    return (
        <section className="panel landmarks-panel">
            <div className="section-row">
                <div>
                    <h2>Уникальные объекты</h2>
                    <p className="muted">
                        Все типы объектов, найденные в видео. Модель размечает
                        классы, поэтому один пункт может объединять несколько
                        похожих объектов. Нажмите на кадр или таймкод, чтобы
                        перейти к нему.
                    </p>
                </div>
                <span className="landmarks-total">
                    {objects.length} типов
                </span>
            </div>

            <div className="landmark-groups">
                {groups.map((group) => (
                    <section className="landmark-group" key={group.category}>
                        <h3>{CATEGORY_LABELS[group.category]}</h3>

                        <div className="landmark-list">
                            {group.items.map((item) => {
                                const timestamps = Array.isArray(item.timestamps)
                                    ? item.timestamps
                                    : [];

                                const confidence = Number(item.mean_confidence);

                                return (
                                    <article className="landmark-card" key={item.label}>
                                        {item.best_frame && (
                                            <button
                                                className="landmark-thumb"
                                                onClick={() => onSeek(item.best_timestamp ?? timestamps[0] ?? 0)}
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
                                                {Number.isFinite(confidence) && confidence > 0
                                                    ? ` · уверенность ${Math.round(confidence * 100)}%`
                                                    : ""}
                                            </p>

                                            <div className="landmark-times">
                                                {timestamps.slice(0, 8).map((timestamp) => (
                                                    <button
                                                        className="interval-chip"
                                                        key={timestamp}
                                                        onClick={() => onSeek(timestamp)}
                                                    >
                                                        {formatTime(timestamp)}
                                                    </button>
                                                ))}

                                                {timestamps.length > 8 && (
                                                    <span className="muted">
                                                        +{timestamps.length - 8}
                                                    </span>
                                                )}
                                            </div>
                                        </div>
                                    </article>
                                );
                            })}
                        </div>
                    </section>
                ))}
            </div>
        </section>
    );
}
