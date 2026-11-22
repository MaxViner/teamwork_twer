import { useEffect, useMemo, useState } from "react";
import { fetchMapQuery } from "../../api/jobs.js";
import "./mapQuery.css";

const TITLES = {
    former_or_abandoned_settlement: "Бывшая или заброшенная деревня",
    manor_or_estate_site_mentioned: "Усадьба / усадебный дом",
    church_or_church_site_mentioned: "Церковь / церковное место",
    river_or_stream_mentioned: "Река / ручей",
    road_mentioned: "Дорога",
    historic_map_mentioned: "Историческая карта",
    historical_house_count_claim: "Число домов на старой карте",
    house_count_claim_unlinked_to_map: "Число домов (связь с картой не установлена)",
};

const RELATIONS = {
    near_claimed_by_speaker: "Автор говорит, что объекты рядом; расстояние неизвестно",
    possibly_near_claimed_by_speaker: "Предположение автора о близости; не подтверждено",
    co_mentioned_only: "Объекты названы вместе; их соседство не установлено",
};

function formatTime(value) {
    const seconds = Number(value);
    if (!Number.isFinite(seconds) || seconds < 0) return "таймкод неизвестен";
    const total = Math.round(seconds * 1000);
    const hours = Math.floor(total / 3_600_000);
    const minutes = Math.floor((total % 3_600_000) / 60_000);
    const secs = Math.floor((total % 60_000) / 1000);
    const millis = total % 1000;
    return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}.${String(millis).padStart(3, "0")}`;
}

function artifactUrl(jobId, value) {
    if (typeof value !== "string" || !value.startsWith("runs/")) return null;
    const parts = value.split("/");
    if (parts.some((part) => !part || part === "." || part === ".." || part.includes("\\"))) return null;
    return `/api/jobs/${encodeURIComponent(jobId)}/files/${parts.map(encodeURIComponent).join("/")}`;
}

export default function MapQueryPanel({ job, onSeek }) {
    const jobId = job?.id;
    const stageKey = Object.entries(job?.stages || {})
        .map(([name, stage]) => `${name}:${stage?.status}:${stage?.result_run_id || ""}`)
        .join("|");
    const [manualRefresh, setManualRefresh] = useState(0);
    const [payload, setPayload] = useState(null);
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (!jobId) { setPayload(null); return undefined; }
        const controller = new AbortController();
        setLoading(true);
        setError("");
        fetchMapQuery(jobId, { signal: controller.signal })
            .then((data) => { if (!controller.signal.aborted) setPayload(data); })
            .catch((reason) => {
                if (!controller.signal.aborted) setError(reason.message || "Не удалось загрузить поисковую гипотезу.");
            })
            .finally(() => { if (!controller.signal.aborted) setLoading(false); });
        return () => controller.abort();
    }, [jobId, job?.status, stageKey, manualRefresh]);

    const claims = useMemo(() => new Map((payload?.claims || []).map((item) => [item.id, item])), [payload]);
    const query = payload?.map_queries || {};
    const requirements = query.requirements || [];
    const relations = query.relations || [];
    const scenes = payload?.scenes || [];

    if (!jobId) return null;
    return (
        <section className="panel map-query-panel" aria-labelledby="map-query-title">
            <div className="section-row">
                <div>
                    <h2 id="map-query-title">Гипотеза для поиска на карте</h2>
                    <p className="muted">Поисковое задание по речи и кадрам; это не найденная точка и не проверка карты.</p>
                </div>
                <div className="toolbar">
                    {query.region && <span className="insight-chip">Регион из видео: {query.region}</span>}
                    <button type="button" onClick={() => setManualRefresh((value) => value + 1)} disabled={loading}>
                        Обновить гипотезу
                    </button>
                </div>
            </div>

            {loading && <p className="muted">Собираю зацепки…</p>}
            {error && <p className="muted" role="alert">{error}</p>}
            {!loading && !error && payload && (
                <>
                    {query.status === "no_geographic_evidence" ? (
                        <p className="muted">В распознанных материалах пока нет географических зацепок.</p>
                    ) : (
                        <>
                            {query.region_status === "conflicting_region_mentions" && (
                                <p className="map-query-warning">В видео названы разные регионы: {query.conflicting_region_mentions.join(", ")}. Не используйте регион как жёсткий фильтр.</p>
                            )}
                            {requirements.length > 0 && (
                                <div className="map-query-grid">
                                    {requirements.map((item) => (
                                        <article className="map-query-card" key={item.key}>
                                            <strong>{TITLES[item.key] || item.key}</strong>
                                            <span>{(item.values || []).map(String).join(" · ") || "упомянуто"}</span>
                                            <small>{item.evidence_status === "mentioned_not_externally_verified" ? "Упоминание в видео · внешне не проверено" : "Требует проверки"}</small>
                                            {(item.claim_ids || []).map((id) => claims.get(id)).filter(Boolean).slice(0, 2).map((claim) => (
                                                <div className="map-query-evidence" key={claim.id}>
                                                    {(claim.support || []).slice(0, 1).map((support, index) => (
                                                        <div key={`${claim.id}-${index}`}>
                                                            <button type="button" className="insight-time" disabled={!Number.isFinite(Number(support.start))} onClick={() => onSeek?.(Number(support.start))}>
                                                                {formatTime(support.start)}
                                                            </button>
                                                            <span>{support.source === "speech" ? "Речь" : "OCR"}: «{support.quote}»</span>
                                                        </div>
                                                    ))}
                                                </div>
                                            ))}
                                        </article>
                                    ))}
                                </div>
                            )}

                            {relations.length > 0 && (
                                <div className="map-query-block">
                                    <h3>Пространственные утверждения</h3>
                                    <ul className="insight-list">
                                        {relations.map((item) => (
                                            <li key={item.claim_id}>
                                                <strong>{item.subject} — {RELATIONS[item.relation] || item.relation} — {item.object}</strong>
                                                <small> Расстояние и направление не определены.</small>
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            )}

                            {query.search_phrases?.length > 0 && (
                                <div className="map-query-block">
                                    <h3>Готовый поисковый запрос</h3>
                                    {query.search_phrases.map((phrase) => (
                                        <div className="map-query-phrase" key={phrase}>
                                            <p>{phrase}</p>
                                            <a className="button-link" href={`https://www.openstreetmap.org/search?query=${encodeURIComponent(phrase)}`} target="_blank" rel="noreferrer">Искать в OpenStreetMap</a>
                                        </div>
                                    ))}
                                    <p className="muted">Ссылка лишь открывает внешний поиск. Сервис не запрашивал OSM и не подтверждал совпадения.</p>
                                </div>
                            )}

                            {scenes.map((scene) => (
                                <div className="map-query-block" key={scene.id}>
                                    <h3>{scene.id} · {formatTime(scene.start)}–{formatTime(scene.end)}</h3>
                                    <p className="muted">Временное соседство реплик и кадров — не доказательство, что объекты показаны вместе.</p>
                                    <div className="map-query-frames">
                                        {(scene.frame_candidates || []).slice(0, 3).map((frame) => {
                                            const src = artifactUrl(jobId, frame.artifact);
                                            return (
                                                <button className="map-query-frame" type="button" key={`${scene.id}-${frame.timestamp}-${frame.artifact}`} onClick={() => onSeek?.(frame.timestamp)}>
                                                    {src ? <img src={src} alt={`Кадр ${formatTime(frame.timestamp)}`} loading="lazy" /> : null}
                                                    <span>{formatTime(frame.timestamp)}</span>
                                                </button>
                                            );
                                        })}
                                    </div>
                                </div>
                            ))}
                        </>
                    )}
                    <details className="map-query-details">
                        <summary>Ограничения и формат</summary>
                        <ul>{(query.notes || payload.limits || []).map((note) => <li key={note}>{note}</li>)}</ul>
                        <p>Координаты карты: не рассчитаны. Внешние источники проверены: нет.</p>
                    </details>
                </>
            )}
        </section>
    );
}
