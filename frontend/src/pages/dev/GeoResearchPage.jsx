import { useEffect, useState } from "react";
import { fetchGeoMeta, runGeoResearch } from "../../api/dev.js";


const EMPTY_POINT = {
    name: "",
    lat: "",
    lon: "",
    azimuth: "",
};


function splitList(value) {
    return value
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
}


function TriangulationEditor({ points, onChange }) {
    const update = (index, field, value) => {
        onChange(points.map((point, position) => (
            position === index
                ? { ...point, [field]: value }
                : point
        )));
    };

    return (
        <div className="dev-points">
            {points.map((point, index) => (
                <div key={index} className="dev-point-row">
                    <input
                        placeholder="Название"
                        value={point.name}
                        onChange={(event) => update(
                            index,
                            "name",
                            event.target.value,
                        )}
                    />
                    <input
                        placeholder="Широта"
                        value={point.lat}
                        onChange={(event) => update(
                            index,
                            "lat",
                            event.target.value,
                        )}
                    />
                    <input
                        placeholder="Долгота"
                        value={point.lon}
                        onChange={(event) => update(
                            index,
                            "lon",
                            event.target.value,
                        )}
                    />
                    <input
                        placeholder="Азимут, °"
                        value={point.azimuth}
                        onChange={(event) => update(
                            index,
                            "azimuth",
                            event.target.value,
                        )}
                    />
                    <button
                        type="button"
                        onClick={() => onChange(
                            points.filter((_, position) => (
                                position !== index
                            )),
                        )}
                    >
                        Убрать
                    </button>
                </div>
            ))}

            <button
                type="button"
                onClick={() => onChange([...points, { ...EMPTY_POINT }])}
            >
                Добавить ориентир
            </button>
        </div>
    );
}


export default function GeoResearchPage() {
    const [meta, setMeta] = useState(null);
    const [species, setSpecies] = useState("ель, сосна, берёза");
    const [landmarks, setLandmarks] = useState(
        "церковь, водонапорная башня",
    );
    const [traces, setTraces] = useState(
        "фундаменты, развилка дорог",
    );
    const [sounds, setSounds] = useState("колокол, поезд");
    const [region, setRegion] = useState("Тверская область");
    const [district, setDistrict] = useState("Максатихинский район");
    const [latitude, setLatitude] = useState("");
    const [longitude, setLongitude] = useState("");
    const [date, setDate] = useState("2024-07-15");
    const [time, setTime] = useState("15:30");
    const [utcOffset, setUtcOffset] = useState(3);
    const [points, setPoints] = useState([]);
    const [result, setResult] = useState(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");


    useEffect(() => {
        fetchGeoMeta()
            .then(setMeta)
            .catch((err) => setError(err.message));
    }, []);


    const submit = async (event) => {
        event.preventDefault();
        setBusy(true);
        setError("");

        try {
            setResult(await runGeoResearch({
                species: splitList(species),
                landmarks: splitList(landmarks),
                traces: splitList(traces),
                sounds: splitList(sounds),
                region: region || null,
                district: district || null,
                latitude: latitude ? Number(latitude) : null,
                longitude: longitude ? Number(longitude) : null,
                date: date || null,
                time: time || null,
                utc_offset: Number(utcOffset),
                triangulation_points: points
                    .filter((point) => (
                        point.lat && point.lon && point.azimuth
                    ))
                    .map((point) => ({
                        name: point.name || null,
                        lat: Number(point.lat),
                        lon: Number(point.lon),
                        azimuth: Number(point.azimuth),
                    })),
            }));
        } catch (err) {
            setError(err.message);
        } finally {
            setBusy(false);
        }
    };


    return (
        <section className="panel">
            <h2>Карт-исследование места</h2>

            <p className="muted">
                Отдельная задача, не связанная с видео: растительность
                сужает регион, ориентиры и следы проверяются слоями
                OSM → Wikimapia → Генштаб → кадастр → спутник.
                Результат — гипотеза и план проверки, а не координата.
            </p>

            <form className="dev-card" onSubmit={submit}>
                <div className="dev-form-grid">
                    <label className="dev-field">
                        Породы деревьев
                        <input
                            value={species}
                            onChange={(event) => setSpecies(
                                event.target.value,
                            )}
                        />
                    </label>

                    <label className="dev-field">
                        Ориентиры горизонта
                        <input
                            value={landmarks}
                            onChange={(event) => setLandmarks(
                                event.target.value,
                            )}
                        />
                    </label>

                    <label className="dev-field">
                        Следы деятельности
                        <input
                            value={traces}
                            onChange={(event) => setTraces(
                                event.target.value,
                            )}
                        />
                    </label>

                    <label className="dev-field">
                        Звуки
                        <input
                            value={sounds}
                            onChange={(event) => setSounds(
                                event.target.value,
                            )}
                        />
                    </label>

                    <label className="dev-field">
                        Регион
                        <input
                            value={region}
                            onChange={(event) => setRegion(
                                event.target.value,
                            )}
                        />
                    </label>

                    <label className="dev-field">
                        Район
                        <input
                            value={district}
                            onChange={(event) => setDistrict(
                                event.target.value,
                            )}
                        />
                    </label>

                    <label className="dev-field">
                        Широта
                        <input
                            value={latitude}
                            onChange={(event) => setLatitude(
                                event.target.value,
                            )}
                        />
                    </label>

                    <label className="dev-field">
                        Долгота
                        <input
                            value={longitude}
                            onChange={(event) => setLongitude(
                                event.target.value,
                            )}
                        />
                    </label>

                    <label className="dev-field">
                        Дата
                        <input
                            type="date"
                            value={date}
                            onChange={(event) => setDate(
                                event.target.value,
                            )}
                        />
                    </label>

                    <label className="dev-field">
                        Время
                        <input
                            type="time"
                            value={time}
                            onChange={(event) => setTime(
                                event.target.value,
                            )}
                        />
                    </label>

                    <label className="dev-field">
                        Часовой пояс
                        <input
                            type="number"
                            step="0.5"
                            value={utcOffset}
                            onChange={(event) => setUtcOffset(
                                event.target.value,
                            )}
                        />
                    </label>
                </div>

                <h3>Триангуляция по известным ориентирам</h3>

                <p className="muted">
                    Азимут задаётся от камеры на ориентир: 0° — север,
                    90° — восток. Нужно минимум два ориентира.
                </p>

                <TriangulationEditor
                    points={points}
                    onChange={setPoints}
                />

                <button
                    className="primary"
                    type="submit"
                    disabled={busy}
                >
                    {busy ? "Считаю…" : "Построить гипотезу"}
                </button>
            </form>

            {error && <div className="error">{error}</div>}

            {result && (
                <>
                    <div className="dev-grid">
                        <div className="dev-card">
                            <h3>Карта</h3>

                            <iframe
                                className="dev-map-frame"
                                title="OpenStreetMap"
                                src={result.map?.embed_url}
                                loading="lazy"
                            />

                            <p className="muted">
                                Центр: {result.map?.latitude},{" "}
                                {result.map?.longitude}
                                {" · "}
                                {result.map?.center_is_hypothesis
                                    ? "точка-гипотеза"
                                    : "обзор региона"}
                            </p>
                        </div>

                        <div className="dev-card">
                            <h3>Гипотеза региона</h3>

                            <dl className="dev-kv">
                                <div className="dev-kv__row">
                                    <dt>зона</dt>
                                    <dd>
                                        {result.region_hypothesis
                                            ?.zone_label_ru}
                                    </dd>
                                </div>
                                <div className="dev-kv__row">
                                    <dt>уверенность</dt>
                                    <dd>
                                        {result.region_hypothesis
                                            ?.confidence}
                                    </dd>
                                </div>
                                <div className="dev-kv__row">
                                    <dt>регион</dt>
                                    <dd>
                                        {result.region_hypothesis?.region
                                            || "—"}
                                    </dd>
                                </div>
                            </dl>

                            <ul className="insight-list">
                                {(result.region_hypothesis?.reasoning
                                    || []).map((item, index) => (
                                    <li key={index}>{item}</li>
                                ))}
                            </ul>

                            {result.region_hypothesis?.candidate_regions
                                ?.length > 0 && (
                                <div className="insight-chips">
                                    {result.region_hypothesis
                                        .candidate_regions
                                        .map((item) => (
                                            <span
                                                key={item}
                                                className="insight-chip"
                                            >
                                                {item}
                                            </span>
                                        ))}
                                </div>
                            )}
                        </div>
                    </div>

                    <div className="dev-card">
                        <h3>Порядок слоёв</h3>

                        <ol className="insight-list">
                            {(result.layer_plan || []).map((layer) => (
                                <li key={layer.id}>
                                    <a
                                        href={layer.url}
                                        target="_blank"
                                        rel="noreferrer"
                                    >
                                        {layer.order}. {layer.name}
                                    </a>
                                    {" — "}
                                    {layer.purpose}
                                </li>
                            ))}
                        </ol>
                    </div>

                    <div className="dev-grid">
                        <div className="dev-card">
                            <h3>Солнце и тени</h3>

                            {result.sun ? (
                                <dl className="dev-kv">
                                    <div className="dev-kv__row">
                                        <dt>азимут солнца</dt>
                                        <dd>
                                            {result.sun.sun_azimuth_deg}°
                                        </dd>
                                    </div>
                                    <div className="dev-kv__row">
                                        <dt>высота</dt>
                                        <dd>
                                            {result.sun.sun_elevation_deg}°
                                        </dd>
                                    </div>
                                    <div className="dev-kv__row">
                                        <dt>азимут тени</dt>
                                        <dd>
                                            {result.sun.shadow_azimuth_deg
                                                ?? "—"}
                                        </dd>
                                    </div>
                                    <div className="dev-kv__row">
                                        <dt>длина тени</dt>
                                        <dd>
                                            ×{result.sun.shadow_length_ratio
                                                ?? "—"}
                                        </dd>
                                    </div>
                                </dl>
                            ) : (
                                <p className="muted">
                                    Нужны координаты и дата.
                                </p>
                            )}

                            {result.sun?.note && (
                                <p className="muted">{result.sun.note}</p>
                            )}
                        </div>

                        <div className="dev-card">
                            <h3>Триангуляция</h3>

                            {result.triangulation?.ok ? (
                                <dl className="dev-kv">
                                    <div className="dev-kv__row">
                                        <dt>точка</dt>
                                        <dd>
                                            {result.triangulation.latitude},{" "}
                                            {result.triangulation.longitude}
                                        </dd>
                                    </div>
                                    <div className="dev-kv__row">
                                        <dt>разброс</dt>
                                        <dd>
                                            {result.triangulation.spread_m} м
                                        </dd>
                                    </div>
                                    <div className="dev-kv__row">
                                        <dt>лучей</dt>
                                        <dd>
                                            {result.triangulation.points_used}
                                        </dd>
                                    </div>
                                </dl>
                            ) : (
                                <p className="muted">
                                    {result.triangulation?.reason
                                        || "Точек пока нет."}
                                </p>
                            )}
                        </div>
                    </div>

                    <div className="dev-card">
                        <h3>Перекрёстные проверки</h3>

                        <ul className="insight-list">
                            {(result.cross_checks || []).map((item) => (
                                <li key={item.id}>
                                    <strong>{item.label}</strong>
                                    {" — "}
                                    {item.why}
                                </li>
                            ))}
                        </ul>
                    </div>

                    <div className="dev-grid">
                        <div className="dev-card">
                            <h3>{result.vanished_villages?.title}</h3>

                            <ol className="insight-list">
                                {(result.vanished_villages?.steps || [])
                                    .map((item, index) => (
                                        <li key={index}>{item}</li>
                                    ))}
                            </ol>
                        </div>

                        <div className="dev-card">
                            <h3>Следующие шаги</h3>

                            <ol className="insight-list">
                                {(result.next_steps || []).map(
                                    (item, index) => (
                                        <li key={index}>{item}</li>
                                    ),
                                )}
                            </ol>

                            <h3>Ограничения</h3>

                            <ul className="insight-list">
                                {(result.limits || []).map(
                                    (item, index) => (
                                        <li key={index}>{item}</li>
                                    ),
                                )}
                            </ul>
                        </div>
                    </div>

                    <div className="dev-card">
                        <h3>Источники</h3>

                        <div className="insight-chips">
                            {(result.vanished_villages?.sources || [])
                                .map((source) => (
                                    <a
                                        key={source.url}
                                        className="insight-chip insight-chip-button"
                                        href={source.url}
                                        target="_blank"
                                        rel="noreferrer"
                                    >
                                        {source.name}
                                    </a>
                                ))}
                        </div>
                    </div>

                    {meta && (
                        <p className="muted">
                            Слоёв: {meta.layers?.length || 0}
                            {" · проверок: "}
                            {meta.cross_checks?.length || 0}
                        </p>
                    )}

                    <details className="dev-card">
                        <summary>Сырой ответ</summary>

                        <pre className="dev-pre">
                            {JSON.stringify(result, null, 2)}
                        </pre>
                    </details>
                </>
            )}
        </section>
    );
}
