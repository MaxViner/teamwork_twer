import { fileUrl } from "../utils/fileUrl.js";
import { formatTime } from "../utils/formatTime.js";


const SPEECH_WINDOW_SECONDS = 10;

const SPEECH_LIMIT = 5;

const MATCH_TOLERANCE_SECONDS = 0.75;

const ROAD_MATCH_TOLERANCE_SECONDS = 0.2;

const ROAD_SEMANTIC_LABELS = [
    "road",
    "path",
    "bridge",
];

const ROAD_SEMANTIC_MIN_PERCENT = 1;


function frameResult(job, stageId) {
    const frames = job?.stages?.[stageId]?.result?.frames;

    return Array.isArray(frames) ? frames : [];
}


function roundTime(value) {
    return Math.round(value * 1000) / 1000;
}


function nearest(items, timestamp) {
    let best = null;

    for (const item of items) {
        const start = Number(item?.start);

        if (!Number.isFinite(start)) {
            continue;
        }

        const diff = Math.abs(start - timestamp);

        if (!best || diff < best.diff) {
            best = {
                item,
                diff,
            };
        }
    }

    if (!best || best.diff > MATCH_TOLERANCE_SECONDS) {
        return null;
    }

    return best.item;
}


function buildFrames(job) {
    const collected = new Map();

    const add = (frame) => {
        const timestamp = Number(frame?.timestamp);

        if (!Number.isFinite(timestamp)) {
            return;
        }

        const key = roundTime(timestamp);

        let entry = collected.get(key);

        if (!entry) {
            entry = {
                timestamp,
                artifact: null,
                objects: [],
                metrics: null,
                descriptors: null,
            };

            collected.set(key, entry);
        }

        if (!entry.artifact && frame.artifact) {
            entry.artifact = frame.artifact;
        }

        if (Array.isArray(frame.objects)) {
            entry.objects = frame.objects;
        }

        if (frame.metrics) {
            entry.metrics = frame.metrics;
        }

        if (frame.descriptors) {
            entry.descriptors = frame.descriptors;
        }
    };

    for (const frame of frameResult(job, "visual_profile")) {
        add(frame);
    }

    for (const frame of frameResult(job, "scene_objects")) {
        add(frame);
    }

    for (const frame of frameResult(job, "ocr")) {
        add(frame);
    }

    return [...collected.values()].sort(
        (a, b) => a.timestamp - b.timestamp,
    );
}


function ocrObservations(job) {
    return (job?.stages?.ocr?.observations || []).filter(
        (item) => item.source === "ocr",
    );
}


function roadSegments(job) {
    const observations = job?.stages?.road_geometry?.observations || [];

    const segments = [];

    for (const observation of observations) {
        const stored = observation?.data?.segments;

        if (Array.isArray(stored) && stored.length) {
            for (const segment of stored) {
                segments.push({
                    ...segment,
                    artifact: segment.artifact || observation.artifact,
                });
            }

            continue;
        }

        if (observation.source !== "road_geometry") {
            continue;
        }

        segments.push({
            start: observation.start,
            end: observation.end,
            text: observation.corrected_text ?? observation.text,
            artifact: observation.artifact,
            confidence: observation.data?.confidence,
            semantic_road_percent: observation.data?.semantic_road_percent,
        });
    }

    const semantic = semanticRoadFrames(job);

    return segments.filter(
        (segment) => roadAllowedByMask(semantic, Number(segment.start)),
    );
}


function semanticRoadFrames(job) {
    const result = job?.stages?.scene_objects?.result;

    if (
        result?.method
        && result.method !== "segformer"
    ) {
        return null;
    }

    const frames = result?.frames;

    if (!Array.isArray(frames) || !frames.length) {
        return null;
    }

    const evidence = new Map();

    for (const frame of frames) {
        const timestamp = Number(frame?.timestamp);

        if (!Number.isFinite(timestamp)) {
            continue;
        }

        let percent = 0;

        for (const item of frame.objects || []) {
            if (ROAD_SEMANTIC_LABELS.includes(item?.label)) {
                percent += Number(item.area_percent) || 0;
            }
        }

        evidence.set(roundTime(timestamp), percent);
    }

    return evidence.size ? evidence : null;
}


function roadAllowedByMask(evidence, timestamp) {
    if (!evidence || !Number.isFinite(timestamp)) {
        return true;
    }

    let nearestKey = null;
    let nearestDiff = Infinity;

    for (const key of evidence.keys()) {
        const diff = Math.abs(key - timestamp);

        if (diff < nearestDiff) {
            nearestKey = key;
            nearestDiff = diff;
        }
    }

    if (
        nearestKey === null
        || nearestDiff > ROAD_MATCH_TOLERANCE_SECONDS
    ) {
        return false;
    }

    return evidence.get(nearestKey) >= ROAD_SEMANTIC_MIN_PERCENT;
}


function speechSegments(job) {
    const observations = job?.stages?.speech?.observations || [];

    const segments = [];

    for (const observation of observations) {
        const stored = observation?.data?.segments;

        if (Array.isArray(stored) && stored.length) {
            for (const segment of stored) {
                segments.push({
                    start: Number(segment.start),
                    end: Number(segment.end ?? segment.start),
                    text: segment.text || "",
                });
            }

            continue;
        }

        if (observation.source === "speech") {
            segments.push({
                start: Number(observation.start),
                end: Number(observation.end ?? observation.start),
                text: observation.corrected_text ?? observation.text ?? "",
            });
        }
    }

    return segments
        .filter((segment) => Number.isFinite(segment.start))
        .sort((a, b) => a.start - b.start);
}


function nearbySpeech(segments, timestamp) {
    const from = timestamp - SPEECH_WINDOW_SECONDS;
    const to = timestamp + SPEECH_WINDOW_SECONDS;

    return segments.filter(
        (segment) => segment.end >= from && segment.start <= to,
    );
}


function speechDistance(segment, timestamp) {
    if (timestamp < segment.start) {
        return segment.start - timestamp;
    }

    if (timestamp > segment.end) {
        return timestamp - segment.end;
    }

    return 0;
}


function closestSpeech(segments, timestamp) {
    return [...segments]
        .sort(
            (a, b) => (
                speechDistance(a, timestamp)
                - speechDistance(b, timestamp)
            ),
        )
        .slice(0, SPEECH_LIMIT)
        .sort((a, b) => a.start - b.start);
}


function sceneFor(intervals, timestamp) {
    if (!Array.isArray(intervals) || !intervals.length) {
        return null;
    }

    let index = intervals.findIndex(
        (interval) => timestamp >= interval[0] && timestamp < interval[1],
    );

    if (index === -1) {
        index = intervals.length - 1;
    }

    return {
        number: index + 1,
        start: intervals[index][0],
        end: intervals[index][1],
    };
}


function cleanRoadText(text) {
    return String(text || "")
        .replace(/^Дорога:\s*/i, "")
        .trim();
}


function formatPercent(value) {
    const number = Number(value);

    return Number.isFinite(number) ? `${number}%` : "";
}


export default function KeyFramesPanel({ job, onSeek }) {
    const frames = buildFrames(job);

    if (!frames.length) {
        return null;
    }

    const ocr = ocrObservations(job);
    const roads = roadSegments(job);
    const speech = speechSegments(job);

    const intervals = job?.stages?.scenes?.result?.intervals || [];

    const hasSpeech = speech.length > 0;

    return (
        <section className="panel keyframes-panel">
            <div className="section-row">
                <div>
                    <h2>Ключевые кадры</h2>
                    <p className="muted">
                        Один сводный вывод на кадр: объекты, визуальный профиль,
                        дорога, текст на кадре и речь в пределах
                        {" "}
                        ±{SPEECH_WINDOW_SECONDS}
                        {" "}
                        секунд. Нажмите на кадр или время, чтобы перейти к нему.
                    </p>
                </div>
                <span className="landmarks-total">
                    {frames.length} кадр.
                    {hasSpeech ? ` · речь ±${SPEECH_WINDOW_SECONDS} с` : ""}
                </span>
            </div>

            <div className="keyframe-list">
                {frames.map((frame, index) => {
                    const objects = [...(frame.objects || [])].sort(
                        (a, b) => (
                            Number(b.area_percent || 0)
                            - Number(a.area_percent || 0)
                        ),
                    );

                    const scene = sceneFor(intervals, frame.timestamp);

                    const road = nearest(roads, frame.timestamp);

                    const texts = ocr
                        .filter((item) => (
                            item.frame_artifact === frame.artifact
                            || Math.abs(item.start - frame.timestamp)
                            <= MATCH_TOLERANCE_SECONDS
                        ))
                        .map((item) => item.corrected_text ?? item.text)
                        .filter(Boolean);

                    const uniqueTexts = [...new Set(texts)];

                    const nearby = nearbySpeech(speech, frame.timestamp);

                    const shownSpeech = closestSpeech(
                        nearby,
                        frame.timestamp,
                    );

                    const descriptors = frame.descriptors || {};

                    const landscape = Array.isArray(descriptors.landscape)
                        ? descriptors.landscape.join(", ")
                        : "";

                    const metrics = frame.metrics || {};

                    return (
                        <article className="keyframe-card" key={frame.timestamp}>
                            {frame.artifact && (
                                <button
                                    className="keyframe-thumb"
                                    onClick={() => onSeek(frame.timestamp)}
                                    title="Перейти к кадру"
                                >
                                    <img
                                        src={fileUrl(job.id, frame.artifact)}
                                        alt={`Кадр ${formatTime(frame.timestamp)}`}
                                        loading="lazy"
                                    />
                                    <span className="keyframe-time">
                                        {formatTime(frame.timestamp)}
                                    </span>
                                </button>
                            )}

                            <div className="keyframe-body">
                                <header className="keyframe-head">
                                    <strong>Кадр {index + 1}</strong>

                                    {scene && (
                                        <span className="keyframe-scene">
                                            Сцена {scene.number}
                                            {" · "}
                                            {formatTime(scene.start)}
                                            –
                                            {formatTime(scene.end)}
                                        </span>
                                    )}
                                </header>

                                <div className="keyframe-row">
                                    <span className="keyframe-label">Объекты</span>

                                    {objects.length ? (
                                        <div className="keyframe-chips">
                                            {objects.slice(0, 6).map((item, itemIndex) => (
                                                <span
                                                    className="keyframe-chip"
                                                    key={`${item.label}-${itemIndex}`}
                                                    title={Number.isFinite(Number(item.confidence))
                                                        ? `Уверенность ${Math.round(Number(item.confidence) * 100)}%`
                                                        : undefined}
                                                >
                                                    {item.label_ru || item.label}
                                                    {formatPercent(item.area_percent)
                                                        ? ` · ${formatPercent(item.area_percent)}`
                                                        : ""}
                                                </span>
                                            ))}

                                            {objects.length > 6 && (
                                                <span className="muted">
                                                    +{objects.length - 6}
                                                </span>
                                            )}
                                        </div>
                                    ) : (
                                        <span className="muted">не найдены</span>
                                    )}
                                </div>

                                {(descriptors.lighting
                                    || descriptors.weather
                                    || descriptors.season
                                    || landscape
                                    || Number.isFinite(Number(metrics.brightness))) && (
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
                                )}

                                <div className="keyframe-row">
                                    <span className="keyframe-label">Дорога</span>

                                    {road ? (
                                        <div className="keyframe-text">
                                            <p>{cleanRoadText(road.text)}</p>

                                            {(road.semantic_road_percent != null
                                                || road.confidence != null) && (
                                                <p className="keyframe-metrics">
                                                    {road.semantic_road_percent != null
                                                        ? `маска дороги ${road.semantic_road_percent}%`
                                                        : ""}
                                                    {road.semantic_road_percent != null
                                                        && road.confidence != null
                                                        ? " · "
                                                        : ""}
                                                    {road.confidence != null
                                                        ? `уверенность ${Math.round(Number(road.confidence) * 100)}%`
                                                        : ""}
                                                </p>
                                            )}
                                        </div>
                                    ) : (
                                        <span className="muted">признаков не найдено</span>
                                    )}
                                </div>

                                {uniqueTexts.length > 0 && (
                                    <div className="keyframe-row">
                                        <span className="keyframe-label">Текст</span>

                                        <div className="keyframe-chips">
                                            {uniqueTexts.slice(0, 3).map((text) => (
                                                <span className="keyframe-chip" key={text}>
                                                    «{text}»
                                                </span>
                                            ))}

                                            {uniqueTexts.length > 3 && (
                                                <span className="muted">
                                                    +{uniqueTexts.length - 3}
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                )}

                                {hasSpeech && (
                                    <div className="keyframe-row keyframe-row-speech">
                                        <span className="keyframe-label">Речь рядом</span>

                                        {nearby.length ? (
                                            <div className="keyframe-speech">
                                                {shownSpeech.map(
                                                    (segment, segmentIndex) => (
                                                        <button
                                                            className="keyframe-speech-row"
                                                            key={`${segment.start}-${segmentIndex}`}
                                                            onClick={() => onSeek(segment.start)}
                                                        >
                                                            <span className="keyframe-speech-time">
                                                                {formatTime(segment.start)}
                                                            </span>
                                                            <span>{segment.text}</span>
                                                        </button>
                                                    ),
                                                )}

                                                {nearby.length > shownSpeech.length && (
                                                    <span className="muted">
                                                        +{nearby.length - shownSpeech.length} реплик
                                                    </span>
                                                )}
                                            </div>
                                        ) : (
                                            <span className="muted">
                                                реплик в окрестности нет
                                            </span>
                                        )}
                                    </div>
                                )}
                            </div>
                        </article>
                    );
                })}
            </div>
        </section>
    );
}
