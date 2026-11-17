const COUNTRY_FALLBACK = "Страна не определена";


function mapLink(latitude, longitude) {
    return (
        "https://www.openstreetmap.org/"
        + `?mlat=${latitude}&mlon=${longitude}`
        + `#map=15/${latitude}/${longitude}`
    );
}


function searchLink(query) {
    return (
        "https://www.openstreetmap.org/search?query="
        + encodeURIComponent(query)
    );
}


function formatPercent(value) {
    const number = Number(value);

    if (!Number.isFinite(number)) {
        return null;
    }

    return `${Math.round(number * 100)}%`;
}


function ProfileLine({ label, children }) {
    if (!children) {
        return null;
    }

    return (
        <p className="dossier-line">
            <span>{label}:</span> {children}
        </p>
    );
}


export default function LocationDossier({ job }) {
    const stage = job?.stages?.location_evidence;
    const dossier = stage?.result?.dossier;

    if (!stage) {
        return null;
    }

    if (!dossier) {
        return (
            <section className="panel">
                <h2>Локационное досье</h2>

                <p className="muted">
                    Досье ещё не сформировано. Этап
                    «Географические улики»
                    {stage.status === "failed"
                        ? " завершился ошибкой."
                        : " не завершён."}
                </p>

                {stage.note && (
                    <p className="muted">{stage.note}</p>
                )}
            </section>
        );
    }

    const coordinates = Array.isArray(dossier.coordinates)
        ? dossier.coordinates
        : [];

    const countries = Array.isArray(dossier.country_candidates)
        ? dossier.country_candidates
        : [];

    const places = Array.isArray(dossier.place_candidates)
        ? dossier.place_candidates
        : [];

    const queries = Array.isArray(dossier.search_queries)
        ? dossier.search_queries
        : [];

    const profile = dossier.profile || {};
    const visual = profile.visual || {};
    const road = profile.road || {};
    const audio = profile.audio || {};

    const landscape = Array.isArray(visual.landscape)
        ? visual.landscape.join(", ")
        : "";

    return (
        <section className="panel dossier">
            <div className="section-row">
                <div>
                    <h2>Локационное досье</h2>

                    <p className="muted">
                        Признаки места и гипотезы для
                        проверки, а не подтверждённый
                        адрес.
                    </p>
                </div>
            </div>

            {dossier.summary && (
                <p className="dossier-summary">
                    {dossier.summary}
                </p>
            )}

            <div className="dossier-grid">
                <article className="dossier-card">
                    <h3>GPS</h3>

                    {coordinates.length === 0 && (
                        <p className="muted">
                            Координат в файле нет.
                        </p>
                    )}

                    {coordinates.map((item, index) => (
                        <p key={`${item.latitude}-${index}`}>
                            <a
                                className="dossier-link"
                                href={mapLink(
                                    item.latitude,
                                    item.longitude,
                                )}
                                target="_blank"
                                rel="noreferrer"
                            >
                                {Number(item.latitude).toFixed(5)},{" "}
                                {Number(item.longitude).toFixed(5)}
                            </a>

                            {item.origin && (
                                <span className="muted">
                                    {" "}
                                    · {item.origin}
                                </span>
                            )}
                        </p>
                    ))}
                </article>

                <article className="dossier-card">
                    <h3>Страны-кандидаты</h3>

                    {countries.length === 0 && (
                        <p className="muted">
                            Недостаточно признаков.
                        </p>
                    )}

                    {countries.map((item) => {
                        const percent = formatPercent(item.score);

                        return (
                            <div
                                className="dossier-country"
                                key={item.code || item.name}
                            >
                                <div className="dossier-country-head">
                                    <span>
                                        {item.name
                                            || item.code
                                            || COUNTRY_FALLBACK}
                                    </span>

                                    {percent && (
                                        <span className="muted">
                                            {percent}
                                        </span>
                                    )}
                                </div>

                                <div className="dossier-bar">
                                    <span
                                        style={{
                                            width: percent || "0%",
                                        }}
                                    />
                                </div>

                                {Array.isArray(item.signals)
                                    && item.signals.length > 0 && (
                                    <ul className="dossier-signals">
                                        {item.signals.map(
                                            (signal) => (
                                                <li key={signal}>
                                                    {signal}
                                                </li>
                                            ),
                                        )}
                                    </ul>
                                )}
                            </div>
                        );
                    })}
                </article>

                <article className="dossier-card">
                    <h3>Места-кандидаты</h3>

                    {places.length === 0 && (
                        <p className="muted">
                            Точные места не выделены.
                        </p>
                    )}

                    {places.map((item) => (
                        <p key={item.text}>
                            {item.text}

                            <span className="muted">
                                {" "}
                                · упоминаний: {item.count}
                            </span>
                        </p>
                    ))}
                </article>

                <article className="dossier-card">
                    <h3>Признаки сцены</h3>

                    <ProfileLine label="Устройство">
                        {profile.device}
                    </ProfileLine>

                    <ProfileLine label="Дата файла">
                        {profile.created_at}
                    </ProfileLine>

                    <ProfileLine label="Сезон">
                        {profile.season}
                    </ProfileLine>

                    <ProfileLine label="Освещённость">
                        {visual.lighting}
                    </ProfileLine>

                    <ProfileLine label="Погода">
                        {visual.weather}
                    </ProfileLine>

                    <ProfileLine label="Ландшафт">
                        {landscape}
                    </ProfileLine>

                    <ProfileLine label="Звук">
                        {audio.environment}
                    </ProfileLine>

                    <ProfileLine label="Дорога">
                        {road.road_detected
                            ? `${road.direction}, линия схода ${
                                road.vanishing_ratio ?? "—"
                            }`
                            : null}
                    </ProfileLine>

                    {!profile.device
                        && !profile.created_at
                        && !visual.lighting
                        && !audio.environment
                        && !road.road_detected && (
                        <p className="muted">
                            Профиль места пока пуст.
                        </p>
                    )}
                </article>
            </div>

            {queries.length > 0 && (
                <div className="dossier-queries">
                    <h3>Что проверить на карте</h3>

                    <div className="dossier-chips">
                        {queries.map((query) => (
                            <a
                                className="dossier-chip"
                                key={query}
                                href={searchLink(query)}
                                target="_blank"
                                rel="noreferrer"
                            >
                                {query}
                            </a>
                        ))}
                    </div>
                </div>
            )}

            {dossier.limitations && (
                <p className="muted dossier-limitations">
                    {dossier.limitations}
                </p>
            )}
        </section>
    );
}
