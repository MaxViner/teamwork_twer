import { useEffect, useRef, useState } from "react";
import { searchJob } from "../api/jobs.js";
import { formatTime } from "../utils/formatTime.js";


const KIND_LABELS = {
    speech: "Речь",
    ocr: "Надпись",
    evidence: "Улика",
    object: "Объект",
    landmark: "Ориентир",
    person: "Человек",
    section: "Раздел",
};


export default function SearchPanel({ job, onSeek, onError }) {
    const [query, setQuery] = useState("");
    const [results, setResults] = useState([]);
    const [loading, setLoading] = useState(false);
    const [touched, setTouched] = useState(false);
    const requestId = useRef(0);

    useEffect(() => {
        setQuery("");
        setResults([]);
        setTouched(false);
    }, [job?.id]);

    useEffect(() => {
        const value = query.trim();

        if (value.length < 2) {
            setResults([]);
            setLoading(false);
            return undefined;
        }

        setLoading(true);

        const timer = window.setTimeout(async () => {
            const id = requestId.current + 1;
            requestId.current = id;

            try {
                const data = await searchJob(job.id, value);

                if (requestId.current !== id) {
                    return;
                }

                setResults(Array.isArray(data?.results) ? data.results : []);
                setTouched(true);

            } catch (error) {
                if (requestId.current === id) {
                    setResults([]);
                    onError?.(error.message);
                }

            } finally {
                if (requestId.current === id) {
                    setLoading(false);
                }
            }
        }, 320);

        return () => window.clearTimeout(timer);
    }, [query, job?.id, onError]);

    if (!job) {
        return null;
    }

    return (
        <section className="panel search-panel">
            <div className="section-row">
                <div>
                    <h2>Поиск внутри видео</h2>
                    <p className="muted">
                        Фраза из речи, надпись, объект, ориентир
                        или раздел — с переходом к нужному моменту.
                    </p>
                </div>

                {touched && !loading && (
                    <span className="insight-count">
                        {results.length} найдено
                    </span>
                )}
            </div>

            <input
                className="insight-search"
                type="search"
                value={query}
                placeholder="Например: церковь, мост, название улицы…"
                onChange={(event) => setQuery(event.target.value)}
            />

            {loading && (
                <p className="muted">Ищу…</p>
            )}

            {!loading && touched && !results.length && (
                <p className="muted">
                    Ничего не найдено. Попробуйте другое слово
                    или короткую фразу.
                </p>
            )}

            {results.length > 0 && (
                <div className="search-results">
                    {results.map((item, index) => (
                        <div
                            className="search-result"
                            key={`${item.kind}-${index}-${item.start ?? "x"}`}
                        >
                            <div className="search-result-meta">
                                <span className="insight-chip">
                                    {KIND_LABELS[item.kind] || item.kind}
                                </span>

                                {item.speaker && (
                                    <span className="insight-chip">
                                        {item.speaker}
                                    </span>
                                )}

                                {item.start !== null && item.start !== undefined && (
                                    <button
                                        className="insight-time"
                                        onClick={() => onSeek(item.start)}
                                    >
                                        {formatTime(item.start)}
                                    </button>
                                )}
                            </div>

                            <p className="search-result-text">
                                {item.text}
                            </p>
                        </div>
                    ))}
                </div>
            )}
        </section>
    );
}
