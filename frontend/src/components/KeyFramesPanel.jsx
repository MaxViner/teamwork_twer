import { useEffect, useMemo, useState } from "react";
import { fileUrl } from "../utils/fileUrl.js";
import { formatTime } from "../utils/formatTime.js";


const GROUP_GAP_SECONDS = 30;
const GROUPS_PER_PAGE = 12;
const FRAMES_PER_PAGE = 18;
const ROAD_TOLERANCE_SECONDS = 0.2;
const ROAD_MIN_PERCENT = 1;


function stageResult(job, stageId) {
    return job?.stages?.[stageId]?.result || {};
}


function collectFrames(job) {
    const collected = new Map();

    for (const stageId of ["visual_profile", "scene_objects", "ocr"]) {
        const frames = stageResult(job, stageId).frames;

        if (!Array.isArray(frames)) {
            continue;
        }

        for (const frame of frames) {
            const timestamp = Number(frame?.timestamp);

            if (!Number.isFinite(timestamp)) {
                continue;
            }

            const key = Math.round(timestamp * 1000);

            const item = collected.get(key) || {
                timestamp,
                artifact: null,
                objects: [],
                descriptors: {},
                metrics: {},
            };

            if (!item.artifact && frame.artifact) {
                item.artifact = frame.artifact;
            }

            if (Array.isArray(frame.objects) && frame.objects.length) {
                item.objects = frame.objects;
            }

            if (frame.descriptors && Object.keys(frame.descriptors).length) {
                item.descriptors = frame.descriptors;
            }

            if (frame.metrics && Object.keys(frame.metrics).length) {
                item.metrics = frame.metrics;
            }

            collected.set(key, item);
        }
    }

    return [...collected.values()].sort((a, b) => a.timestamp - b.timestamp);
}


function sceneIntervals(job) {
    const intervals = stageResult(job, "scenes").intervals;

    if (!Array.isArray(intervals)) {
        return [];
    }

    return intervals
        .filter((value) => Array.isArray(value) && value.length >= 2)
        .map((value) => [Number(value[0]), Number(value[1])])
        .filter(([start, end]) => Number.isFinite(start) && Number.isFinite(end) && end > start)
        .sort((a, b) => a[0] - b[0]);
}


function sceneIndex(intervals, moment) {
    for (let index = 0; index < intervals.length; index += 1) {
        const [start, end] = intervals[index];

        if (start <= moment && moment < end) {
            return index;
        }
    }

    return null;
}


function groupFrames(frames, intervals) {
    const groups = [];

    for (const frame of frames) {
        const index = sceneIndex(intervals, frame.timestamp);
        const key = index === null ? "free" : `scene:${index}`;
        const current = groups[groups.length - 1];

        if (
            !current
            || current.key !== key
            || frame.timestamp - current.end > GROUP_GAP_SECONDS
        ) {
            groups.push({
                key,
                sceneIndexes: index === null ? [] : [index],
                start: frame.timestamp,
                end: frame.timestamp,
                frames: [frame],
            });

            continue;
        }

        current.frames.push(frame);
        current.end = frame.timestamp;

        if (index !== null && !current.sceneIndexes.includes(index)) {
            current.sceneIndexes.push(index);
        }
    }

    return groups.map((group, index) => ({
        ...group,
        number: index + 1,
        sceneNumbers: group.sceneIndexes.map((value) => value + 1),
    }));
}


function semanticRoadMap(job) {
    const stage = job?.stages?.scene_objects;
    const method = stage?.result?.method;

    if (method && method !== "segformer") {
        return null;
    }

    const frames = stage?.result?.frames;

    if (!Array.isArray(frames) || !frames.length) {
        return null;
    }

    const map = new Map();

    for (const frame of frames) {
        const timestamp = Number(frame?.timestamp);

        if (!Number.isFinite(timestamp)) {
            continue;
        }

        let percent = 0;

        for (const item of frame.objects || []) {
            if (["road", "path", "bridge"].includes(item.label)) {
                percent += Number(item.area_percent || 0);
            }
        }

        map.set(Math.round(timestamp * 1000) / 1000, percent);
    }

    return map.size ? map : null;
}


function roadSegments(job) {
    const stage = job?.stages?.road_geometry;

    if (!stage) {
        return [];
    }

    const evidence = semanticRoadMap(job);
    const segments = [];

    for (const observation of stage.observations || []) {
        const stored = observation?.data?.segments;

        if (Array.isArray(stored)) {
            segments.push(...stored);
        }
    }

    return segments
        .map((segment) => ({
            ...segment,
            start: Number(segment.start),
        }))
        .filter((segment) => Number.isFinite(segment.start))
        .filter((segment) => {
            if (!evidence) {
                return true;
            }

            let nearest = null;

            for (const [key, percent] of evidence.entries()) {
                const distance = Math.abs(key - segment.start);

                if (!nearest || distance < nearest.distance) {
                    nearest = { distance, percent };
                }
            }

            return Boolean(
                nearest
                && nearest.distance <= ROAD_TOLERANCE_SECONDS
                && nearest.percent >= ROAD_MIN_PERCENT,
            );
        })
        .sort((a, b) => a.start - b.start);
}


function nearestRoad(segments, timestamp) {
    let best = null;

    for (const segment of segments) {
        const distance = Math.abs(segment.start - timestamp);

        if (!best || distance < best.distance) {
            best = { segment, distance };
        }
    }

    return best && best.distance <= ROAD_TOLERANCE_SECONDS ? best.segment : null;
}


function objectSummary(frames) {
    const collected = new Map();

    for (const frame of frames) {
        const seen = new Set();

        for (const item of frame.objects || []) {
            const label = item.label_ru || item.label;

            if (!label || seen.has(label)) {
                continue;
            }

            seen.add(label);

            const entry = collected.get(label) || {
                label,
                count: 0,
                area: 0,
            };

            entry.count += 1;
            entry.area = Math.max(entry.area, Number(item.area_percent || 0));
            collected.set(label, entry);
        }
    }

    return [...collected.values()]
        .sort((a, b) => b.count - a.count || b.area - a.area)
        .slice(0, 6);
}


function visualFor(frames) {
    const parts = [];
    const first = frames.find((frame) => frame.descriptors?.lighting);
    const weather = frames.find((frame) => frame.descriptors?.weather);
    const season = frames.find((frame) => frame.descriptors?.season);

    if (first?.descriptors?.lighting) {
        parts.push(first.descriptors.lighting);
    }

    if (weather?.descriptors?.weather) {
        parts.push(weather.descriptors.weather);
    }

    if (season?.descriptors?.season) {
        parts.push(season.descriptors.season);
    }

    return parts.join(" · ");
}


function paginate(items, page, size) {
    const pages = Math.max(1, Math.ceil(items.length / size));
    const current = Math.min(Math.max(1, page), pages);

    return {
        pages,
        items: items.slice((current - 1) * size, current * size),
    };
}


function Pager({ page, pages, onChange, label }) {
    if (pages <= 1) {
        return null;
    }

    return (
        <div className="kf-pager">
            <button
                className="kf-pager-button"
                disabled={page <= 1}
                onClick={() => onChange(page - 1)}
            >
                ←
            </button>

            <span className="muted">
                {label}: {page} / {pages}
            </span>

            <button
                className="kf-pager-button"
                disabled={page >= pages}
                onClick={() => onChange(page + 1)}
            >
                →
            </button>
        </div>
    );
}


export default function KeyFramesPanel({ job, onSeek }) {
    const frames = useMemo(() => collectFrames(job), [job]);
    const intervals = useMemo(() => sceneIntervals(job), [job]);
    const groups = useMemo(() => groupFrames(frames, intervals), [frames, intervals]);
    const roads = useMemo(() => roadSegments(job), [job]);

    const [groupPage, setGroupPage] = useState(1);
    const [framePage, setFramePage] = useState(1);
    const [selected, setSelected] = useState(1);

    useEffect(() => {
        setGroupPage(1);
        setFramePage(1);
        setSelected(1);
    }, [job?.id]);

    const groupsPage = paginate(groups, groupPage, GROUPS_PER_PAGE);
    const group = groups.find((item) => item.number === selected) || groups[0];

    const framesPage = paginate(group?.frames || [], framePage, FRAMES_PER_PAGE);

    useEffect(() => {
        setFramePage(1);
    }, [selected, groupPage]);

    useEffect(() => {
        setGroupPage(Math.max(1, Math.ceil(selected / GROUPS_PER_PAGE)));
    }, [selected]);

    if (!frames.length) {
        return null;
    }

    const summaryObjects = objectSummary(group?.frames || []);
    const visual = visualFor(group?.frames || []);
    const groupRoads = (group?.frames || [])
        .map((frame) => nearestRoad(roads, frame.timestamp))
        .filter(Boolean);
    const roadLabels = [...new Set(groupRoads.map((item) => item.curve_label || item.direction).filter(Boolean))];

    return (
        <section className="panel keyframes-panel">
            <div className="section-row">
                <div>
                    <h2>Ключевые кадры по локациям</h2>
                    <p className="muted">
                        Кадры объединены по сценам и непрерывным участкам.
                        Внутри локации — компактная лента; откройте нужную
                        группу и пролистайте кадры.
                    </p>
                </div>

                <span className="kf-total">
                    {frames.length} кадр. · {groups.length} локац.
                </span>
            </div>

            <div className="kf-group-bar">
                <Pager
                    page={groupPage}
                    pages={groupsPage.pages}
                    onChange={setGroupPage}
                    label="Локации"
                />

                <div className="kf-group-chips">
                    {groupsPage.items.map((item) => (
                        <button
                            className={`kf-group-chip${item.number === group?.number ? " is-active" : ""}`}
                            key={`${item.key}-${item.number}`}
                            onClick={() => setSelected(item.number)}
                            title={`${formatTime(item.start)} – ${formatTime(item.end)}`}
                        >
                            <strong>Локация {item.number}</strong>
                            <span>
                                {formatTime(item.start)}
                                {" · "}
                                {item.frames.length} кадр.
                            </span>
                        </button>
                    ))}
                </div>
            </div>

            {group && (
                <div className="kf-detail">
                    <div className="kf-detail-head">
                        <div>
                            <h3>
                                Локация {group.number} · {formatTime(group.start)}
                                {group.end > group.start ? ` – ${formatTime(group.end)}` : ""}
                            </h3>

                            <p className="muted">
                                {group.frames.length} кадр.
                                {group.sceneNumbers.length
                                    ? ` · сцена ${group.sceneNumbers.join(", ")}`
                                    : ""}
                            </p>
                        </div>

                        <Pager
                            page={selected}
                            pages={groups.length}
                            onChange={setSelected}
                            label="Локация"
                        />
                    </div>

                    <div className="kf-summary">
                        {summaryObjects.length > 0 && (
                            <p>
                                <span className="kf-label">Видно:</span>{" "}
                                {summaryObjects
                                    .map((item) => `${item.label} (${item.count})`)
                                    .join(", ")}
                            </p>
                        )}

                        {visual && (
                            <p>
                                <span className="kf-label">Кадр:</span> {visual}
                            </p>
                        )}

                        {roadLabels.length > 0 && (
                            <p>
                                <span className="kf-label">Дорога:</span>{" "}
                                {roadLabels.join(", ")}
                            </p>
                        )}
                    </div>

                    <div className="kf-frame-grid">
                        {framesPage.items.map((frame) => {
                            const road = nearestRoad(roads, frame.timestamp);
                            const objects = (frame.objects || [])
                                .slice()
                                .sort((a, b) => Number(b.area_percent || 0) - Number(a.area_percent || 0))
                                .slice(0, 3)
                                .map((item) => item.label_ru || item.label)
                                .filter(Boolean);

                            return (
                                <button
                                    className="kf-frame"
                                    key={frame.timestamp}
                                    onClick={() => onSeek(frame.timestamp)}
                                    title={
                                        objects.length
                                            ? `${formatTime(frame.timestamp)} · ${objects.join(", ")}`
                                            : formatTime(frame.timestamp)
                                    }
                                >
                                    <img
                                        src={fileUrl(job.id, frame.artifact)}
                                        alt={`Кадр ${formatTime(frame.timestamp)}`}
                                        loading="lazy"
                                    />

                                    <span className="kf-frame-time">
                                        {formatTime(frame.timestamp)}
                                    </span>

                                    {road && (
                                        <span className="kf-frame-road">
                                            {road.curve_label || road.direction}
                                        </span>
                                    )}
                                </button>
                            );
                        })}
                    </div>

                    <Pager
                        page={framesPage.pages === 0 ? 1 : framePage}
                        pages={framesPage.pages}
                        onChange={setFramePage}
                        label="Кадры"
                    />
                </div>
            )}
        </section>
    );
}
