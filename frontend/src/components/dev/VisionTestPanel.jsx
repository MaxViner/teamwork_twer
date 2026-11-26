import { useRef, useState } from "react";
import { analyzeVision, describeImage } from "../../api/dev.js";


const PRIORITY_LABELS = {
    high: "сильная",
    medium: "средняя",
    low: "слабая",
};


function percent(value) {
    if (value === null || value === undefined) {
        return "—";
    }

    return `${Math.round(Number(value) * 100)}%`;
}


function ModelStatus({ status }) {
    if (!status) {
        return null;
    }

    const detector = status.detector || {};
    const segmenter = status.segmenter || {};

    return (
        <div className="dev-card">
            <h3>Состояние моделей</h3>

            <dl className="dev-kv">
                <dt>Grounding DINO</dt>
                <dd>
                    {detector.loaded ? "загружен" : "не загружен"}
                    {detector.error ? ` · ${detector.error}` : ""}
                </dd>

                <dt>SAM2</dt>
                <dd>
                    {segmenter.loaded ? "загружен" : "не загружен"}
                    {segmenter.error ? ` · ${segmenter.error}` : ""}
                </dd>

                <dt>Пороги</dt>
                <dd>
                    box {status.thresholds?.box_threshold}
                    {" · "}
                    text {status.thresholds?.text_threshold}
                </dd>
            </dl>
        </div>
    );
}


function ClueOverlay({ result, preview }) {
    const size = result?.image_size || [];
    const width = Number(size[0]) || 0;
    const height = Number(size[1]) || 0;
    const clues = result?.geo_clues || [];

    if (!preview) {
        return null;
    }

    return (
        <div className="dev-image">
            <img src={preview} alt="Кадр для анализа" />

            {width > 0 && height > 0 && clues.length > 0 && (
                <svg
                    className="dev-overlay"
                    viewBox={`0 0 ${width} ${height}`}
                    preserveAspectRatio="none"
                >
                    {clues.map((clue, index) => {
                        const polygon = clue.polygon || [];

                        if (polygon.length < 3) {
                            return null;
                        }

                        const points = polygon
                            .map(([x, y]) => `${x},${y}`)
                            .join(" ");

                        return (
                            <polygon
                                key={`${clue.label}-${index}`}
                                points={points}
                                fill="rgba(92, 233, 255, 0.16)"
                                stroke="rgba(92, 233, 255, 0.95)"
                                strokeWidth={Math.max(2, width / 400)}
                            />
                        );
                    })}
                </svg>
            )}
        </div>
    );
}


function ClueList({ clues }) {
    if (!clues?.length) {
        return <p className="muted">Улики не найдены.</p>;
    }

    return (
        <div className="dev-clues">
            {clues.map((clue, index) => (
                <article
                    key={`${clue.label}-${index}`}
                    className="dev-card dev-clue"
                >
                    <div className="dev-clue__head">
                        <strong>{clue.label_ru || clue.label}</strong>
                        <span className={`dev-pill dev-pill--${clue.match_priority}`}>
                            {PRIORITY_LABELS[clue.match_priority]
                                || clue.match_priority}
                        </span>
                    </div>

                    <dl className="dev-kv">
                        <dt>confidence</dt>
                        <dd>{percent(clue.confidence)}</dd>

                        <dt>видимость</dt>
                        <dd>{percent(clue.visibility_fraction)}</dd>

                        <dt>сложность</dt>
                        <dd>{clue.shape_complexity}</dd>

                        <dt>тип</dt>
                        <dd>{clue.type}</dd>

                        <dt>сегмент</dt>
                        <dd>{clue.segmented ? "SAM2" : "bbox"}</dd>
                    </dl>

                    {clue.description && (
                        <p className="muted">{clue.description}</p>
                    )}
                </article>
            ))}
        </div>
    );
}


export default function VisionTestPanel() {
    const [file, setFile] = useState(null);
    const [preview, setPreview] = useState("");
    const [result, setResult] = useState(null);
    const [aiResult, setAiResult] = useState(null);
    const [prompt, setPrompt] = useState("");
    const [error, setError] = useState("");
    const [busy, setBusy] = useState("");
    const inputRef = useRef(null);


    const handleFile = (event) => {
        const selected = event.target.files?.[0];

        if (!selected) {
            return;
        }

        setFile(selected);
        setPreview(URL.createObjectURL(selected));
        setResult(null);
        setAiResult(null);
        setError("");
    };


    const runLocal = async () => {
        if (!file) {
            setError("Выберите изображение.");
            return;
        }

        setBusy("local");
        setError("");

        try {
            setResult(await analyzeVision(file));
        } catch (err) {
            setError(err.message);
        } finally {
            setBusy("");
        }
    };


    const runAi = async () => {
        if (!file) {
            setError("Выберите изображение.");
            return;
        }

        setBusy("ai");
        setError("");

        try {
            setAiResult(await describeImage(file, prompt));
        } catch (err) {
            setError(err.message);
        } finally {
            setBusy("");
        }
    };


    const analysis = aiResult?.analysis || {};
    const metrics = result?.metrics?.metrics || result?.metrics || {};
    const descriptors = result?.descriptors
        || result?.metrics?.descriptors
        || {};
    const palette = metrics.palette || [];


    return (
        <section className="panel">
            <h2>Визуальный анализ кадра</h2>

            <p className="muted">
                Локальный прогон всех визуальных сервисов на одном
                изображении: метрики, гео-улики Grounding DINO + SAM2,
                SegFormer, лица и тайминги. AI-описание — отдельная
                кнопка, внешний провайдер не обязателен.
            </p>

            <div className="dev-toolbar">
                <input
                    ref={inputRef}
                    type="file"
                    accept="image/*"
                    onChange={handleFile}
                />

                <button
                    className="primary"
                    disabled={busy !== "" || !file}
                    onClick={runLocal}
                >
                    {busy === "local"
                        ? "Анализирую…"
                        : "Локальный анализ"}
                </button>

                <button
                    disabled={busy !== "" || !file}
                    onClick={runAi}
                >
                    {busy === "ai"
                        ? "AI думает…"
                        : "AI описание"}
                </button>
            </div>

            <label className="dev-field">
                Дополнительный запрос для AI
                <textarea
                    value={prompt}
                    onChange={(event) => setPrompt(event.target.value)}
                    placeholder="Например: определи вероятную страну и тип места"
                />
            </label>

            {error && <div className="error">{error}</div>}

            {preview && (
                <ClueOverlay
                    result={result}
                    preview={preview}
                />
            )}

            {result && (
                <>
                    {result.errors?.length > 0 && (
                        <div className="dev-card dev-card--error">
                            <h3>Ошибки функций</h3>

                            <ul className="insight-list">
                                {result.errors.map((item, index) => (
                                    <li key={index}>
                                        <strong>{item.function}</strong>
                                        {": "}
                                        {item.error}
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}

                    <div className="dev-grid">
                        <ModelStatus status={result.model_status} />

                        <div className="dev-card">
                            <h3>Тайминги</h3>

                            <dl className="dev-kv">
                                {Object.entries(
                                    result.inference_time_ms || {},
                                ).map(([key, value]) => (
                                    <div key={key} className="dev-kv__row">
                                        <dt>{key}</dt>
                                        <dd>{value} мс</dd>
                                    </div>
                                ))}
                            </dl>
                        </div>

                        <div className="dev-card">
                            <h3>Метрики</h3>

                            <dl className="dev-kv">
                                {Object.entries(metrics)
                                    .filter(([key]) => key !== "palette")
                                    .map(([key, value]) => (
                                        <div key={key} className="dev-kv__row">
                                            <dt>{key}</dt>
                                            <dd>{value}</dd>
                                        </div>
                                    ))}
                            </dl>

                            {palette.length > 0 && (
                                <div className="dev-palette">
                                    {palette.map((item, index) => (
                                        <span
                                            key={index}
                                            title={
                                                item.hex
                                                || item.color
                                                || ""
                                            }
                                            style={{
                                                background: item.hex
                                                    || item.color,
                                            }}
                                        />
                                    ))}
                                </div>
                            )}
                        </div>

                        <div className="dev-card">
                            <h3>Дескрипторы</h3>

                            <ul className="insight-list">
                                {Object.entries(descriptors).map(
                                    ([key, value]) => (
                                        <li key={key}>
                                            <strong>{key}</strong>
                                            {": "}
                                            {Array.isArray(value)
                                                ? value.join(", ")
                                                : String(value)}
                                        </li>
                                    ),
                                )}
                            </ul>
                        </div>
                    </div>

                    {result.frame_summary && (
                        <div className="dev-card">
                            <h3>Сводка кадра</h3>

                            <dl className="dev-kv">
                                {Object.entries(result.frame_summary).map(
                                    ([key, value]) => (
                                        <div key={key} className="dev-kv__row">
                                            <dt>{key}</dt>
                                            <dd>
                                                {Array.isArray(value)
                                                    ? value.join(", ")
                                                    : String(value)}
                                            </dd>
                                        </div>
                                    ),
                                )}
                            </dl>
                        </div>
                    )}

                    <div className="dev-card">
                        <h3>
                            Гео-улики
                            {result.geo_clues?.length
                                ? ` (${result.geo_clues.length})`
                                : ""}
                        </h3>

                        {result.geo_clue_error && (
                            <p className="danger">
                                {result.geo_clue_error}
                            </p>
                        )}

                        <ClueList clues={result.geo_clues} />
                    </div>

                    <div className="dev-grid">
                        <div className="dev-card">
                            <h3>Лица</h3>

                            {result.faces?.length ? (
                                <ul className="insight-list">
                                    {result.faces.map((face, index) => (
                                        <li key={index}>
                                            {face.label || "лицо"}
                                            {" · "}
                                            {percent(face.confidence)}
                                        </li>
                                    ))}
                                </ul>
                            ) : (
                                <p className="muted">
                                    Лица не найдены.
                                </p>
                            )}
                        </div>

                        <div className="dev-card">
                            <h3>SegFormer</h3>

                            <p className="muted">
                                На CPU один кадр может считаться
                                минуту и дольше — это нормально для
                                этой модели.
                            </p>

                            {result.segments?.length ? (
                                <ul className="insight-list">
                                    {result.segments.map((item, index) => (
                                        <li key={index}>
                                            {item.label_ru || item.label}
                                            {" · "}
                                            {item.area_percent}%
                                        </li>
                                    ))}
                                </ul>
                            ) : (
                                <p className="muted">
                                    Сегменты не найдены.
                                </p>
                            )}
                        </div>
                    </div>

                    <details className="dev-card">
                        <summary>Сырой ответ</summary>

                        <pre className="dev-pre">
                            {JSON.stringify(result, null, 2)}
                        </pre>
                    </details>
                </>
            )}

            {aiResult && (
                <div className="dev-card">
                    <h3>AI-описание</h3>

                    <p>{analysis.short_description}</p>
                    <p className="muted">
                        {analysis.detailed_description}
                    </p>

                    {analysis.main_objects?.length > 0 && (
                        <div className="insight-chips">
                            {analysis.main_objects.map((item, index) => (
                                <span key={index} className="insight-chip">
                                    {item.name}
                                    <small>
                                        {percent(item.confidence)}
                                    </small>
                                </span>
                            ))}
                        </div>
                    )}

                    {analysis.location_clues?.length > 0 && (
                        <ul className="insight-list">
                            {analysis.location_clues.map((item, index) => (
                                <li key={index}>{item}</li>
                            ))}
                        </ul>
                    )}
                </div>
            )}
        </section>
    );
}
