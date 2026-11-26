import { useState } from "react";
import {
    analyzeOdometry,
    analyzeOdometryPair,
    uploadOdometryVideo,
} from "../../api/dev.js";


function formatNumber(value, digits = 2) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
        return "—";
    }

    return Number(value).toFixed(digits);
}


function Diagnostics({ data }) {
    if (!data) {
        return null;
    }

    return (
        <dl className="dev-kv">
            <div className="dev-kv__row">
                <dt>успешных пар</dt>
                <dd>{data.successful_pairs}</dd>
            </div>
            <div className="dev-kv__row">
                <dt>пропущено</dt>
                <dd>{data.skipped_pairs}</dd>
            </div>
            <div className="dev-kv__row">
                <dt>средняя доля инлайеров</dt>
                <dd>{formatNumber(data.mean_quality, 3)}</dd>
            </div>
            <div className="dev-kv__row">
                <dt>средние инлайеры</dt>
                <dd>{formatNumber(data.mean_inliers, 1)}</dd>
            </div>
            <div className="dev-kv__row">
                <dt>средние совпадения</dt>
                <dd>{formatNumber(data.mean_matches, 1)}</dd>
            </div>
            <div className="dev-kv__row">
                <dt>средние признаки</dt>
                <dd>{formatNumber(data.mean_features, 0)}</dd>
            </div>
            <div className="dev-kv__row">
                <dt>причины отказов</dt>
                <dd>
                    {Object.entries(data.skipped_reasons || {}).length
                        ? Object.entries(data.skipped_reasons)
                            .map(([key, value]) => `${key}: ${value}`)
                            .join(", ")
                        : "—"}
                </dd>
            </div>
        </dl>
    );
}


function TrajectoryStats({ trajectory, scale }) {
    if (!trajectory) {
        return null;
    }

    return (
        <dl className="dev-kv">
            <div className="dev-kv__row">
                <dt>точек маршрута</dt>
                <dd>{trajectory.points?.length || 0}</dd>
            </div>
            <div className="dev-kv__row">
                <dt>длина пути (условно)</dt>
                <dd>{formatNumber(trajectory.path_length)}</dd>
            </div>
            <div className="dev-kv__row">
                <dt>смещение (условно)</dt>
                <dd>{formatNumber(trajectory.displacement)}</dd>
            </div>
            <div className="dev-kv__row">
                <dt>длина ≈ м</dt>
                <dd>{formatNumber(trajectory.path_length_approx_m, 1)}</dd>
            </div>
            <div className="dev-kv__row">
                <dt>суммарный поворот</dt>
                <dd>{formatNumber(trajectory.total_turn_deg, 1)}°</dd>
            </div>
            <div className="dev-kv__row">
                <dt>единицы</dt>
                <dd>{trajectory.units || "relative"}</dd>
            </div>
            <div className="dev-kv__row">
                <dt>масштаб</dt>
                <dd>
                    {scale?.source || "—"}
                    {" ×"}
                    {formatNumber(scale?.m_per_unit, 2)}
                </dd>
            </div>
        </dl>
    );
}


function PairsTable({ pairs, skipped }) {
    const rows = (pairs || []).slice(0, 40);
    const failed = (skipped || []).slice(0, 20);

    return (
        <>
            {rows.length > 0 && (
                <div className="dev-scroll">
                    <table className="dev-table">
                        <thead>
                            <tr>
                                <th>пара</th>
                                <th>t</th>
                                <th>инлайеры</th>
                                <th>quality</th>
                                <th>совпадения</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows.map((pair, index) => (
                                <tr key={index}>
                                    <td>
                                        {pair.from_timestamp}
                                        {" → "}
                                        {pair.to_timestamp}
                                    </td>
                                    <td>
                                        {Array.isArray(pair.t)
                                            ? pair.t
                                                .map((value) => formatNumber(value, 2))
                                                .join(", ")
                                            : "—"}
                                    </td>
                                    <td>{pair.inliers}</td>
                                    <td>{formatNumber(pair.quality, 3)}</td>
                                    <td>{pair.matches ?? "—"}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            {failed.length > 0 && (
                <div className="dev-scroll">
                    <table className="dev-table">
                        <thead>
                            <tr>
                                <th>пропуск</th>
                                <th>причина</th>
                                <th>признаки</th>
                                <th>совпадения</th>
                            </tr>
                        </thead>
                        <tbody>
                            {failed.map((pair, index) => (
                                <tr key={index}>
                                    <td>
                                        {pair.from_timestamp}
                                        {" → "}
                                        {pair.to_timestamp}
                                    </td>
                                    <td>{pair.reason}</td>
                                    <td>
                                        {pair.diagnostics?.features_a ?? "—"}
                                    </td>
                                    <td>
                                        {pair.diagnostics?.matches ?? "—"}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </>
    );
}


export default function OdometryLabPage() {
    const [mode, setMode] = useState("video");

    // видео
    const [lab, setLab] = useState(null);
    const [file, setFile] = useState(null);
    const [count, setCount] = useState(16);
    const [includeClues, setIncludeClues] = useState(false);
    const [clueFrames, setClueFrames] = useState(6);
    const [cameraHeight, setCameraHeight] = useState(1.2);
    const [result, setResult] = useState(null);
    const [version, setVersion] = useState(0);
    const [busy, setBusy] = useState("");
    const [error, setError] = useState("");

    // пара кадров
    const [frameA, setFrameA] = useState(null);
    const [frameB, setFrameB] = useState(null);
    const [pair, setPair] = useState(null);


    const upload = async () => {
        if (!file) {
            setError("Выберите видео.");
            return;
        }

        setBusy("upload");
        setError("");

        try {
            const data = await uploadOdometryVideo(file);
            setLab(data);
            setResult(null);
        } catch (err) {
            setError(err.message);
        } finally {
            setBusy("");
        }
    };


    const analyze = async () => {
        if (!lab) {
            return;
        }

        setBusy("analyze");
        setError("");
        setResult(null);

        try {
            const data = await analyzeOdometry(lab.id, {
                count: Number(count),
                include_clues: includeClues,
                clue_frames: Number(clueFrames),
                camera_height_m: Number(cameraHeight),
            });

            setResult(data);
            setVersion((current) => current + 1);
        } catch (err) {
            setError(err.message);
        } finally {
            setBusy("");
        }
    };


    const analyzePair = async () => {
        if (!frameA || !frameB) {
            setError("Выберите два кадра.");
            return;
        }

        setBusy("pair");
        setError("");
        setPair(null);

        try {
            setPair(await analyzeOdometryPair(frameA, frameB));
        } catch (err) {
            setError(err.message);
        } finally {
            setBusy("");
        }
    };


    return (
        <section className="panel">
            <h2>Одометрия и BEV</h2>

            <p className="muted">
                Топологическая карта «маршрут + ключевые якоря».
                Длина шага из recoverPose нормирована, поэтому метры
                здесь — грубая оценка, а не измерение. На BEV попадают
                только сильные ориентиры: дома, фундаменты, мосты,
                промышленные объекты и природные якоря.
            </p>

            <div className="dev-tabs">
                <button
                    className={mode === "video" ? "is-active" : ""}
                    onClick={() => setMode("video")}
                >
                    Видео
                </button>
                <button
                    className={mode === "pair" ? "is-active" : ""}
                    onClick={() => setMode("pair")}
                >
                    Пара кадров
                </button>
            </div>

            {error && <div className="error">{error}</div>}

            {mode === "video" && (
                <>
                    <div className="dev-card">
                        <h3>Видео</h3>

                        <div className="dev-toolbar">
                            <input
                                type="file"
                                accept="video/*"
                                onChange={(event) => setFile(
                                    event.target.files?.[0] || null,
                                )}
                            />

                            <button
                                className="primary"
                                disabled={busy !== "" || !file}
                                onClick={upload}
                            >
                                {busy === "upload"
                                    ? "Загружаю…"
                                    : "Загрузить"}
                            </button>
                        </div>

                        {lab && (
                            <p className="muted">
                                {lab.filename}
                                {" · "}
                                {formatNumber(lab.duration, 1)} с
                                {" · "}
                                id {lab.id}
                            </p>
                        )}
                    </div>

                    {lab && (
                        <div className="dev-card">
                            <h3>Параметры анализа</h3>

                            <div className="dev-form-grid">
                                <label className="dev-field">
                                    Кадров
                                    <input
                                        type="number"
                                        min="2"
                                        max="48"
                                        value={count}
                                        onChange={(event) => setCount(
                                            event.target.value,
                                        )}
                                    />
                                </label>

                                <label className="dev-field">
                                    Якорных кадров
                                    <input
                                        type="number"
                                        min="0"
                                        max="24"
                                        value={clueFrames}
                                        onChange={(event) => setClueFrames(
                                            event.target.value,
                                        )}
                                    />
                                </label>

                                <label className="dev-field">
                                    Высота камеры, м
                                    <input
                                        type="number"
                                        min="0.2"
                                        max="10"
                                        step="0.1"
                                        value={cameraHeight}
                                        onChange={(event) => setCameraHeight(
                                            event.target.value,
                                        )}
                                    />
                                </label>
                            </div>

                            <label className="dev-check">
                                <input
                                    type="checkbox"
                                    checked={includeClues}
                                    onChange={(event) => setIncludeClues(
                                        event.target.checked,
                                    )}
                                />
                                Считать гео-улики для якорей (медленно,
                                нужны модели)
                            </label>

                            <button
                                className="primary"
                                disabled={busy !== ""}
                                onClick={analyze}
                            >
                                {busy === "analyze"
                                    ? "Считаю одометрию…"
                                    : "Запустить"}
                            </button>
                        </div>
                    )}

                    {result && (
                        <>
                            <div className="dev-grid">
                                <div className="dev-card">
                                    <h3>BEV</h3>

                                    {result.bev_url ? (
                                        <img
                                            className="dev-bev"
                                            src={`${result.bev_url}?v=${version}`}
                                            alt="BEV карта"
                                        />
                                    ) : (
                                        <p className="muted">
                                            BEV не построен: мало точек
                                            траектории.
                                        </p>
                                    )}

                                    {result.bev && (
                                        <dl className="dev-kv">
                                            <div className="dev-kv__row">
                                                <dt>режим</dt>
                                                <dd>{result.bev.mode}</dd>
                                            </div>
                                            <div className="dev-kv__row">
                                                <dt>якорей</dt>
                                                <dd>{result.bev.anchor_count}</dd>
                                            </div>
                                            <div className="dev-kv__row">
                                                <dt>отброшено улик</dt>
                                                <dd>
                                                    {result.bev.ignored_clue_count}
                                                </dd>
                                            </div>
                                        </dl>
                                    )}
                                </div>

                                <div className="dev-card">
                                    <h3>Диагностика пар</h3>

                                    <Diagnostics
                                        data={result.odometry?.diagnostics}
                                    />
                                </div>

                                <div className="dev-card">
                                    <h3>Траектория</h3>

                                    <TrajectoryStats
                                        trajectory={result.odometry?.trajectory}
                                        scale={result.odometry?.scale}
                                    />
                                </div>
                            </div>

                            {result.bev?.anchors?.length > 0 && (
                                <div className="dev-card">
                                    <h3>Ключевые якоря</h3>

                                    <div className="dev-clues">
                                        {result.bev.anchors.map(
                                            (anchor, index) => (
                                                <article
                                                    key={index}
                                                    className="dev-card dev-clue"
                                                >
                                                    <div className="dev-clue__head">
                                                        <strong>
                                                            {index + 1}.{" "}
                                                            {anchor.label_ru
                                                                || anchor.label}
                                                        </strong>
                                                        <span className="dev-pill">
                                                            {anchor.type}
                                                        </span>
                                                    </div>

                                                    <p className="muted">
                                                        confidence{" "}
                                                        {formatNumber(
                                                            anchor.confidence,
                                                            2,
                                                        )}
                                                        {" · кадров "}
                                                        {anchor.frame_count}
                                                        {" · t "}
                                                        {anchor.timestamp}
                                                    </p>
                                                </article>
                                            ),
                                        )}
                                    </div>
                                </div>
                            )}

                            <div className="dev-card">
                                <h3>Пары кадров</h3>

                                <PairsTable
                                    pairs={result.odometry?.pairs}
                                    skipped={result.odometry?.skipped}
                                />
                            </div>

                            {result.odometry?.note && (
                                <p className="muted">
                                    {result.odometry.note}
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
                </>
            )}

            {mode === "pair" && (
                <>
                    <div className="dev-card">
                        <h3>Два кадра</h3>

                        <div className="dev-form-grid">
                            <label className="dev-field">
                                Кадр A
                                <input
                                    type="file"
                                    accept="image/*"
                                    onChange={(event) => setFrameA(
                                        event.target.files?.[0] || null,
                                    )}
                                />
                            </label>

                            <label className="dev-field">
                                Кадр B
                                <input
                                    type="file"
                                    accept="image/*"
                                    onChange={(event) => setFrameB(
                                        event.target.files?.[0] || null,
                                    )}
                                />
                            </label>
                        </div>

                        <button
                            className="primary"
                            disabled={busy !== "" || !frameA || !frameB}
                            onClick={analyzePair}
                        >
                            {busy === "pair"
                                ? "Считаю позу…"
                                : "Оценить позу"}
                        </button>
                    </div>

                    {pair && (
                        <div className="dev-card">
                            <h3>
                                Результат:{" "}
                                {pair.ok ? "поза найдена" : "отказ"}
                            </h3>

                            {pair.reason && (
                                <p className="danger">
                                    причина: {pair.reason}
                                </p>
                            )}

                            {pair.ok && (
                                <dl className="dev-kv">
                                    <div className="dev-kv__row">
                                        <dt>инлайеры</dt>
                                        <dd>{pair.result?.inliers}</dd>
                                    </div>
                                    <div className="dev-kv__row">
                                        <dt>quality</dt>
                                        <dd>
                                            {formatNumber(
                                                pair.result?.quality,
                                                3,
                                            )}
                                        </dd>
                                    </div>
                                    <div className="dev-kv__row">
                                        <dt>R</dt>
                                        <dd>
                                            {JSON.stringify(
                                                pair.result?.R,
                                            )}
                                        </dd>
                                    </div>
                                    <div className="dev-kv__row">
                                        <dt>t (единичный)</dt>
                                        <dd>
                                            {JSON.stringify(
                                                pair.result?.t,
                                            )}
                                        </dd>
                                    </div>
                                </dl>
                            )}

                            <h3>Диагностика</h3>

                            <dl className="dev-kv">
                                {Object.entries(
                                    pair.diagnostics || {},
                                ).map(([key, value]) => (
                                    <div key={key} className="dev-kv__row">
                                        <dt>{key}</dt>
                                        <dd>{String(value)}</dd>
                                    </div>
                                ))}
                            </dl>

                            <details>
                                <summary>Сырой ответ</summary>

                                <pre className="dev-pre">
                                    {JSON.stringify(pair, null, 2)}
                                </pre>
                            </details>
                        </div>
                    )}
                </>
            )}
        </section>
    );
}
