import {
    useCallback,
    useEffect,
    useRef,
    useState,
} from "react";
import { Link } from "react-router-dom";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

import PageHeader from "../layout/PageHeader.jsx";
import {
    createGhostMark,
    deleteGhostMark,
    fetchGhostMarks,
    fetchGhostPlaces,
    fetchGhostRoads,
    fetchGhostStatus,
    fetchGhosts,
    generateGhostMap,
} from "../api/ghostMap.js";
import "../styles/dev.css";
import "../styles/ghostMap.css";


const OSM_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const SAT_URL = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/"
    + "World_Imagery/MapServer/tile/{z}/{y}/{x}"
);
const DEFAULT_MENDE = "https://retromap.ru/141853/{z}/{x}/{y}.png";
const MENDE_KEY = "mende_url";
const EMPTY = { type: "FeatureCollection", features: [] };


function line(text, className = "") {
    const node = document.createElement("div");

    if (className) {
        node.className = className;
    }

    node.textContent = text;

    return node;
}


function popupButton(label, onClick) {
    const button = document.createElement("button");

    button.type = "button";
    button.className = "primary ghost-map__popup-button";
    button.textContent = label;
    button.addEventListener("click", onClick);

    return button;
}


function formatDate(value) {
    if (!value) {
        return "—";
    }

    try {
        return new Date(value).toLocaleString();
    } catch {
        return value;
    }
}


export default function GhostMapPage() {
    const containerRef = useRef(null);
    const mapRef = useRef(null);
    const layersRef = useRef({});
    const manualRef = useRef(false);
    const pollTimer = useRef(null);

    const [status, setStatus] = useState(null);
    const [places, setPlaces] = useState(EMPTY);
    const [ghosts, setGhosts] = useState(EMPTY);
    const [marks, setMarks] = useState([]);
    const [roads, setRoads] = useState(null);
    const [hasData, setHasData] = useState(false);
    const [error, setError] = useState("");
    const [notice, setNotice] = useState("");

    const [base, setBase] = useState("osm");
    const [mendeEnabled, setMendeEnabled] = useState(true);
    const [mendeInput, setMendeInput] = useState(
        () => localStorage.getItem(MENDE_KEY) || DEFAULT_MENDE,
    );
    const [mendeUrl, setMendeUrl] = useState(
        () => localStorage.getItem(MENDE_KEY) || DEFAULT_MENDE,
    );
    const [mendeOpacity, setMendeOpacity] = useState(55);

    const [uyezd, setUyezd] = useState("");
    const [useNominatim, setUseNominatim] = useState(false);
    const [manualMode, setManualMode] = useState(false);
    const [roadsLoading, setRoadsLoading] = useState(false);

    manualRef.current = manualMode;


    const pollStatus = useCallback(async () => {
        try {
            const data = await fetchGhostStatus();

            setStatus(data);

            if (data.running) {
                pollTimer.current = setTimeout(pollStatus, 3000);
            }
        } catch (requestError) {
            setError(requestError.message);
        }
    }, []);


    const loadMarks = useCallback(async () => {
        try {
            const data = await fetchGhostMarks();
            setMarks(data.marks || []);
        } catch (requestError) {
            setError(requestError.message);
        }
    }, []);


    const loadMapData = useCallback(async () => {
        try {
            const [placesData, ghostsData] = await Promise.all([
                fetchGhostPlaces(),
                fetchGhosts(),
            ]);

            setPlaces(placesData);
            setGhosts(ghostsData);
            setHasData(true);
        } catch (requestError) {
            setHasData(false);

            if (!String(requestError.message).includes("не генерировалась")) {
                setError(requestError.message);
            }
        }
    }, []);


    useEffect(() => {
        pollStatus();
        loadMarks();
        loadMapData();

        return () => clearTimeout(pollTimer.current);
    }, [pollStatus, loadMarks, loadMapData]);


    const generatedAt = status?.meta?.generated_at;

    useEffect(() => {
        if (generatedAt) {
            loadMapData();
        }
    }, [generatedAt, loadMapData]);


    // ── карта ────────────────────────────────────────────

    useEffect(() => {
        if (!containerRef.current || mapRef.current) {
            return undefined;
        }

        const map = L.map(containerRef.current, {
            center: [57.0, 35.6],
            zoom: 8,
            zoomControl: true,
        });

        mapRef.current = map;
        L.control.scale({ imperial: false }).addTo(map);

        map.on("click", async (event) => {
            if (!manualRef.current) {
                return;
            }

            const name = window.prompt("Название призрака");

            if (!name) {
                return;
            }

            try {
                const data = await createGhostMark({
                    name,
                    lat: event.latlng.lat,
                    lon: event.latlng.lng,
                    note: "Ручная отметка с карты",
                });

                setMarks(data.marks || []);
                setNotice(`Отметка «${name}» сохранена.`);
            } catch (requestError) {
                setError(requestError.message);
            }
        });

        return () => {
            map.remove();
            mapRef.current = null;
            layersRef.current = {};
        };
    }, []);


    // базовая карта
    useEffect(() => {
        const map = mapRef.current;

        if (!map) {
            return;
        }

        const layers = layersRef.current;

        if (layers.base) {
            map.removeLayer(layers.base);
        }

        layers.base = L.tileLayer(
            base === "sat" ? SAT_URL : OSM_URL,
            {
                maxZoom: 19,
                attribution: base === "sat"
                    ? "Esri World Imagery"
                    : "© OpenStreetMap",
            },
        ).addTo(map);

        // Базовая карта добавлена последней — вернуть слой Менде наверх.
        layers.mende?.bringToFront();
    }, [base]);


    // слой Менде
    useEffect(() => {
        const map = mapRef.current;

        if (!map) {
            return;
        }

        const layers = layersRef.current;

        if (layers.mende) {
            map.removeLayer(layers.mende);
            layers.mende = null;
        }

        if (!mendeEnabled || !mendeUrl) {
            return;
        }

        layers.mende = L.tileLayer(mendeUrl, {
            maxZoom: 18,
            opacity: mendeOpacity / 100,
            attribution: "Менде",
        }).addTo(map);
    }, [mendeEnabled, mendeUrl]);


    useEffect(() => {
        layersRef.current.mende?.setOpacity(mendeOpacity / 100);
    }, [mendeOpacity]);


    // привидения
    useEffect(() => {
        const map = mapRef.current;

        if (!map) {
            return;
        }

        const layers = layersRef.current;

        if (layers.ghosts) {
            map.removeLayer(layers.ghosts);
            layers.ghosts = null;
        }

        if (!ghosts?.features?.length) {
            return;
        }

        layers.ghosts = L.geoJSON(ghosts, {
            pointToLayer: (feature, latlng) => L.circleMarker(
                latlng,
                {
                    radius: 9,
                    color: "#cc0000",
                    fillColor: "#cc0000",
                    fillOpacity: 0.2,
                    weight: 2,
                },
            ),
            onEachFeature: (feature, layer) => {
                const properties = feature.properties || {};
                const [lon, lat] = feature.geometry.coordinates;
                const content = document.createElement("div");

                content.append(
                    line(properties.name || "без названия", "ghost-map__popup-title"),
                    line(
                        `${properties.kind || ""} при ${properties.position || ""}`,
                        "muted",
                    ),
                    line(`уезд: ${properties.uyezd || "—"}`, "muted"),
                    line(
                        properties.match === "nominatim"
                            ? "координаты приблизительные (Nominatim)"
                            : "",
                        "muted",
                    ),
                );

                content.append(popupButton(
                    "Подтвердить вручную",
                    async () => {
                        try {
                            const data = await createGhostMark({
                                name: properties.name || "без названия",
                                lat,
                                lon,
                                note: "Подтверждено с карты привидений",
                            });

                            setMarks(data.marks || []);
                            setNotice(
                                `«${properties.name}» подтверждён вручную.`,
                            );
                            map.closePopup();
                        } catch (requestError) {
                            setError(requestError.message);
                        }
                    },
                ));

                layer.bindPopup(content);
            },
        }).addTo(map);
    }, [ghosts]);


    // совпавшие НП
    useEffect(() => {
        const map = mapRef.current;

        if (!map) {
            return;
        }

        const layers = layersRef.current;

        if (layers.places) {
            map.removeLayer(layers.places);
            layers.places = null;
        }

        if (!places?.features?.length) {
            return;
        }

        layers.places = L.geoJSON(places, {
            pointToLayer: (feature, latlng) => L.circleMarker(
                latlng,
                {
                    radius: 4,
                    color: "#008800",
                    fillColor: "#00aa44",
                    fillOpacity: 0.8,
                    weight: 1,
                },
            ),
            onEachFeature: (feature, layer) => {
                const properties = feature.properties || {};

                layer.bindPopup(
                    `${properties.name || "НП"}`
                    + (properties.modern_name
                        ? ` → ${properties.modern_name}`
                        : ""),
                );
            },
        }).addTo(map);
    }, [places]);


    // ручные отметки
    useEffect(() => {
        const map = mapRef.current;

        if (!map) {
            return;
        }

        const layers = layersRef.current;

        if (layers.marks) {
            map.removeLayer(layers.marks);
            layers.marks = null;
        }

        if (!marks.length) {
            return;
        }

        layers.marks = L.geoJSON(
            {
                type: "FeatureCollection",
                features: marks.map((mark) => ({
                    type: "Feature",
                    geometry: {
                        type: "Point",
                        coordinates: [mark.lon, mark.lat],
                    },
                    properties: mark,
                })),
            },
            {
                pointToLayer: (feature, latlng) => L.circleMarker(
                    latlng,
                    {
                        radius: 7,
                        color: "#1f5fd0",
                        fillColor: "#3d7bff",
                        fillOpacity: 0.9,
                        weight: 2,
                    },
                ),
                onEachFeature: (feature, layer) => {
                    const mark = feature.properties || {};
                    const content = document.createElement("div");

                    content.append(
                        line(mark.name || "отметка", "ghost-map__popup-title"),
                        line(mark.note || "", "muted"),
                    );

                    if (mark.id) {
                        content.append(popupButton(
                            "Удалить отметку",
                            async () => {
                                try {
                                    const data = await deleteGhostMark(mark.id);

                                    setMarks(data.marks || []);
                                    map.closePopup();
                                } catch (requestError) {
                                    setError(requestError.message);
                                }
                            },
                        ));
                    }

                    layer.bindPopup(content);
                },
            },
        ).addTo(map);
    }, [marks]);


    // дороги и деревни по экрану
    useEffect(() => {
        const map = mapRef.current;

        if (!map) {
            return;
        }

        const layers = layersRef.current;

        if (layers.roads) {
            map.removeLayer(layers.roads);
            layers.roads = null;
        }

        if (!roads?.features?.length) {
            return;
        }

        layers.roads = L.geoJSON(roads, {
            style: (feature) => (
                feature.geometry.type === "LineString"
                    ? {
                        color: "#2f6df6",
                        weight: 3,
                        opacity: 0.85,
                    }
                    : {}
            ),
            pointToLayer: (feature, latlng) => L.circleMarker(
                latlng,
                {
                    radius: 4,
                    color: "#1c8f4a",
                    fillColor: "#1c8f4a",
                    fillOpacity: 0.85,
                    weight: 1,
                },
            ),
            onEachFeature: (feature, layer) => {
                const properties = feature.properties || {};
                const title = properties.name
                    || properties.highway
                    || properties.place
                    || "объект";

                layer.bindPopup(title);
            },
        }).addTo(map);
    }, [roads]);


    // ── действия ─────────────────────────────────────────

    const handleGenerate = async () => {
        setError("");
        setNotice("");

        try {
            await generateGhostMap({
                uyezd: uyezd || null,
                use_nominatim: useNominatim,
            });

            setStatus((current) => ({
                ...(current || {}),
                running: true,
                state: "running",
                progress: 0,
                message: "Задача принята.",
            }));

            clearTimeout(pollTimer.current);
            pollTimer.current = setTimeout(pollStatus, 1500);
        } catch (requestError) {
            setError(requestError.message);
        }
    };


    const handleRoads = async () => {
        const map = mapRef.current;

        if (!map) {
            return;
        }

        setRoadsLoading(true);
        setError("");

        try {
            const bbox = map.getBounds().toBBoxString();
            setRoads(await fetchGhostRoads(bbox));
            setNotice("Дороги и деревни загружены для видимого экрана.");
        } catch (requestError) {
            setError(requestError.message);
        } finally {
            setRoadsLoading(false);
        }
    };


    const handleMendeApply = () => {
        const value = mendeInput.trim() || DEFAULT_MENDE;

        setMendeInput(value);
        setMendeUrl(value);
        localStorage.setItem(MENDE_KEY, value);
    };


    const handleExport = () => {
        const features = [
            ...(ghosts.features || []),
            ...marks.map((mark) => ({
                type: "Feature",
                geometry: {
                    type: "Point",
                    coordinates: [mark.lon, mark.lat],
                },
                properties: {
                    ...mark,
                    layer: "manual",
                },
            })),
        ];

        const payload = {
            type: "FeatureCollection",
            features,
        };
        const blob = new Blob(
            [JSON.stringify(payload, null, 2)],
            { type: "application/geo+json" },
        );
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");

        link.href = url;
        link.download = "ghost_map.geojson";
        link.click();
        URL.revokeObjectURL(url);
    };


    const counts = status?.meta?.counts || {};
    const progress = Math.max(
        0,
        Math.min(100, Number(status?.progress) || 0),
    );
    const running = Boolean(status?.running);


    return (
        <main className="app">
            <PageHeader />

            <section className="panel ghost-map">
                <div className="ghost-map__head">
                    <div>
                        <h2>Карта привидений</h2>

                        <p className="muted">
                            НП Тверской губернии 1859 г.: зелёные точки
                            найдены в OSM сейчас, красные круги — только
                            в списках 1859 г. Слои: OSM или спутник,
                            дороги, Менде и ручные отметки.
                        </p>
                    </div>

                    <Link
                        to="/"
                        className="insight-chip insight-chip-button"
                    >
                        К анализу видео
                    </Link>
                </div>

                {error && <div className="error">{error}</div>}
                {notice && (
                    <div className="ghost-map__notice">{notice}</div>
                )}

                <div className="ghost-map__layout">
                    <aside className="ghost-map__side">
                        <div className="dev-card">
                            <h3>Генерация</h3>

                            <label className="dev-field">
                                Уезд
                                <select
                                    value={uyezd}
                                    onChange={(event) => setUyezd(
                                        event.target.value,
                                    )}
                                >
                                    <option value="">Все уезды</option>
                                    {(status?.uyezds || []).map((name) => (
                                        <option key={name} value={name}>
                                            {name}
                                        </option>
                                    ))}
                                </select>
                            </label>

                            <label className="dev-check">
                                <input
                                    type="checkbox"
                                    checked={useNominatim}
                                    onChange={(event) => setUseNominatim(
                                        event.target.checked,
                                    )}
                                />
                                Геокодировать несовпавшие через
                                Nominatim (медленно)
                            </label>

                            <button
                                className="primary"
                                type="button"
                                disabled={running}
                                onClick={handleGenerate}
                            >
                                {running
                                    ? "Генерация идёт…"
                                    : "Запустить генерацию"}
                            </button>

                            <div className="ghost-map__status">
                                <div className="ghost-map__status-head">
                                    <strong>
                                        {running
                                            ? "Выполняется"
                                            : status?.state === "failed"
                                                ? "Ошибка"
                                                : "Статус"}
                                    </strong>
                                    <span>{Math.round(progress)}%</span>
                                </div>

                                <div className="ghost-map__bar">
                                    <span style={{ width: `${progress}%` }} />
                                </div>

                                <p className="muted">
                                    {status?.message || "Нет данных."}
                                </p>

                                {status?.error && (
                                    <p className="danger">
                                        {status.error}
                                    </p>
                                )}

                                <dl className="dev-kv">
                                    <div className="dev-kv__row">
                                        <dt>совпало</dt>
                                        <dd>{counts.matched ?? "—"}</dd>
                                    </div>
                                    <div className="dev-kv__row">
                                        <dt>привидений</dt>
                                        <dd>{counts.ghosts ?? "—"}</dd>
                                    </div>
                                    <div className="dev-kv__row">
                                        <dt>без координат</dt>
                                        <dd>{counts.unresolved ?? "—"}</dd>
                                    </div>
                                    <div className="dev-kv__row">
                                        <dt>сгенерировано</dt>
                                        <dd>{formatDate(generatedAt)}</dd>
                                    </div>
                                </dl>
                            </div>
                        </div>

                        <div className="dev-card">
                            <h3>Слои</h3>

                            <div className="dev-tabs">
                                <button
                                    type="button"
                                    className={base === "osm" ? "is-active" : ""}
                                    onClick={() => setBase("osm")}
                                >
                                    OSM
                                </button>
                                <button
                                    type="button"
                                    className={base === "sat" ? "is-active" : ""}
                                    onClick={() => setBase("sat")}
                                >
                                    Спутник
                                </button>
                            </div>

                            <label className="dev-check">
                                <input
                                    type="checkbox"
                                    checked={mendeEnabled}
                                    onChange={(event) => setMendeEnabled(
                                        event.target.checked,
                                    )}
                                />
                                Слой Менде
                            </label>

                            <label className="dev-field">
                                Прозрачность Менде: {mendeOpacity}%
                                <input
                                    type="range"
                                    min="0"
                                    max="100"
                                    value={mendeOpacity}
                                    onChange={(event) => setMendeOpacity(
                                        Number(event.target.value),
                                    )}
                                />
                            </label>

                            <label className="dev-field">
                                Шаблон тайлов Менде
                                <input
                                    value={mendeInput}
                                    onChange={(event) => setMendeInput(
                                        event.target.value,
                                    )}
                                    placeholder={DEFAULT_MENDE}
                                />
                            </label>

                            <button
                                type="button"
                                onClick={handleMendeApply}
                            >
                                Применить шаблон
                            </button>

                            <label className="dev-check">
                                <input
                                    type="checkbox"
                                    checked={manualMode}
                                    onChange={(event) => setManualMode(
                                        event.target.checked,
                                    )}
                                />
                                Ручной режим: клик по карте ставит отметку
                            </label>
                        </div>

                        <div className="dev-card">
                            <h3>Действия</h3>

                            <button
                                type="button"
                                disabled={roadsLoading}
                                onClick={handleRoads}
                            >
                                {roadsLoading
                                    ? "Загружаю дороги…"
                                    : "Загрузить дороги"}
                            </button>

                            <button
                                type="button"
                                onClick={handleExport}
                            >
                                Сохранить GeoJSON
                            </button>

                            {!hasData && (
                                <p className="muted">
                                    Артефактов ещё нет. Запустите
                                    генерацию одного уезда — это быстрее
                                    и безопаснее для сети.
                                </p>
                            )}
                        </div>
                    </aside>

                    <div className="ghost-map__stage">
                        <div
                            ref={containerRef}
                            className="ghost-map__canvas"
                        />
                    </div>
                </div>
            </section>
        </main>
    );
}
