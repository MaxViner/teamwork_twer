import { useEffect, useMemo, useState } from "react";
import { formatTime } from "../../../utils/formatTime.js";


const TURNS_PER_PAGE = 40;
const TURN_GAP_SECONDS = 2;


function speechResult(job) {
    return job?.stages?.speech?.result || {};
}


function speechSegments(job) {
    const segments = speechResult(job).segments;

    if (!Array.isArray(segments)) {
        return [];
    }

    return segments
        .filter((item) => item && item.text)
        .map((item) => ({
            start: Number(item.start) || 0,
            end: Number(item.end) || Number(item.start) || 0,
            text: String(item.text),
            speaker: item.speaker || null,
        }))
        .sort((a, b) => a.start - b.start);
}


function buildTurns(segments) {
    const turns = [];

    for (const item of segments) {
        const current = turns[turns.length - 1];

        if (
            current
            && current.speaker === item.speaker
            && item.start - current.end <= TURN_GAP_SECONDS
        ) {
            current.text += ` ${item.text}`;
            current.end = Math.max(current.end, item.end);
            continue;
        }

        turns.push({
            speaker: item.speaker,
            start: item.start,
            end: item.end,
            text: item.text,
        });
    }

    return turns;
}


function speakerSummary(job) {
    const result = speechResult(job);
    const stored = result.speakers;

    if (Array.isArray(stored) && stored.length) {
        return stored.map((item) => ({
            label: item.label || "Спикер",
            count: item.segment_count || 0,
            pitch: item.mean_pitch_hz,
        }));
    }

    const collected = new Map();

    for (const item of speechSegments(job)) {
        if (!item.speaker) {
            continue;
        }

        const entry = collected.get(item.speaker) || {
            label: item.speaker,
            count: 0,
            pitch: null,
        };

        entry.count += 1;
        collected.set(item.speaker, entry);
    }

    return [...collected.values()];
}


export default function TranscriptPanel({ job, onSeek, embedded = false }) {
    const segments = useMemo(() => speechSegments(job), [job]);
    const turns = useMemo(() => buildTurns(segments), [segments]);
    const speakers = useMemo(() => speakerSummary(job), [job]);

    const [speaker, setSpeaker] = useState("all");
    const [query, setQuery] = useState("");
    const [page, setPage] = useState(1);

    useEffect(() => {
        setSpeaker("all");
        setQuery("");
        setPage(1);
    }, [job?.id]);

    useEffect(() => {
        setPage(1);
    }, [speaker, query]);

    const filtered = useMemo(() => {
        const needle = query.trim().toLowerCase();

        return turns.filter((item) => {
            if (speaker !== "all" && item.speaker !== speaker) {
                return false;
            }

            if (!needle) {
                return true;
            }

            return item.text.toLowerCase().includes(needle);
        });
    }, [turns, speaker, query]);

    if (!segments.length) {
        return null;
    }

    const pages = Math.max(1, Math.ceil(filtered.length / TURNS_PER_PAGE));
    const current = Math.min(page, pages);
    const visible = filtered.slice(
        (current - 1) * TURNS_PER_PAGE,
        current * TURNS_PER_PAGE,
    );

    const method = speechResult(job).speaker_method;
    const hasSpeakers = segments.some((item) => item.speaker);

    return (
        <section className={embedded ? "transcript-embedded" : "panel transcript-panel"}>
            <div className="section-row">
                {!embedded && (
                    <div>
                        <h2>Расшифровка речи</h2>
                        <p className="muted">
                            Полная расшифровка с таймкодами
                            {hasSpeakers ? " и разделением по спикерам" : ""}.
                            Нажмите на время, чтобы перейти к моменту.
                        </p>
                    </div>
                )}

                <span className="insight-count">
                    {turns.length} реплик
                </span>
            </div>

            <div className="transcript-exports">
                <a
                    className="button-link"
                    href={`/api/jobs/${job.id}/transcript.vtt`}
                >
                    Субтитры VTT
                </a>

                <a
                    className="button-link"
                    href={`/api/jobs/${job.id}/transcript.srt`}
                >
                    Субтитры SRT
                </a>

                <a
                    className="button-link"
                    href={`/api/jobs/${job.id}/transcript.json`}
                >
                    Расшифровка JSON
                </a>
            </div>

            {hasSpeakers && (
                <div className="transcript-tools">
                    <div className="insight-chips">
                        <button
                            className={`insight-chip insight-chip-button${speaker === "all" ? " is-active" : ""}`}
                            onClick={() => setSpeaker("all")}
                        >
                            Все
                        </button>

                        {speakers.map((item) => (
                            <button
                                className={`insight-chip insight-chip-button${speaker === item.label ? " is-active" : ""}`}
                                key={item.label}
                                onClick={() => setSpeaker(item.label)}
                                title={item.pitch ? `Высота голоса ≈ ${item.pitch} Гц` : undefined}
                            >
                                {item.label}
                                <small>{item.count}</small>
                            </button>
                        ))}
                    </div>
                </div>
            )}

            <input
                className="insight-search"
                type="search"
                value={query}
                placeholder="Найти фразу в расшифровке"
                onChange={(event) => setQuery(event.target.value)}
            />

            {hasSpeakers && method && (
                <p className="muted transcript-note">
                    Спикеры разделены приблизительно ({method}).
                    Это подсказка для чтения диалога, а не точная
                    диаризация.
                </p>
            )}

            {!visible.length && (
                <p className="muted">Ничего не найдено.</p>
            )}

            <ol className="transcript-list">
                {visible.map((item, index) => (
                    <li
                        className="transcript-row"
                        key={`${item.start}-${index}`}
                    >
                        <button
                            className="insight-time"
                            onClick={() => onSeek(item.start)}
                        >
                            {formatTime(item.start)}
                        </button>

                        <div className="transcript-text">
                            {item.speaker && (
                                <strong className="transcript-speaker">
                                    {item.speaker}:
                                </strong>
                            )}{" "}
                            {item.text}
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
        </section>
    );
}
