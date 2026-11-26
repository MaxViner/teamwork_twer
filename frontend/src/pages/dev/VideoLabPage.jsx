import { useState } from "react";


const FUNCTIONS = [
    { id: "metrics", label: "Метрики кадра" },
    { id: "geo_clues", label: "Гео-улики" },
    { id: "segmentation", label: "SegFormer" },
    { id: "faces", label: "Лица" },
    { id: "ocr", label: "OCR" },
    { id: "all", label: "Все функции" },
];


export default function VideoLabPage() {
    const [lab, setLab] = useState(null);
    const [file, setFile] = useState(null);
    const [timestamp, setTimestamp] = useState(0);
    const [selected, setSelected] = useState(["all"]);
    const [result, setResult] = useState(null);
    const [loading, setLoading] = useState("");
    const [error, setError] = useState("");


    async function upload() {
        setError("");
        setLoading("upload");

        try {
            const body = new FormData();
            body.append("file", file);

            const response = await fetch(
                "/api/dev/video-lab/upload",
                { method: "POST", body },
            );

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || "Ошибка загрузки");
            }

            setLab(data);
            setTimestamp(0);
            setResult(null);

        } catch (requestError) {
            setError(requestError.message);

        } finally {
            setLoading("");
        }
    }


    async function analyze() {
        if (!lab) {
            return;
        }

        setError("");
        setLoading("analyze");
        setResult(null);

        try {
            const response = await fetch(
                `/api/dev/video-lab/${lab.id}/analyze`,
                {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        timestamp: Number(timestamp),
                        functions: selected,
                    }),
                },
            );

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || "Ошибка анализа");
            }

            setResult(data);

        } catch (requestError) {
            setError(requestError.message);

        } finally {
            setLoading("");
        }
    }


    function toggleFunction(id) {
        setSelected((current) => (
            current.includes(id)
                ? current.filter((item) => item !== id)
                : [...current, id]
        ));
    }


    return (
        <section className="panel">
            <h2>Видео-лаб</h2>

            <p className="muted">
                Загрузите короткое видео, выберите таймкод и запустите
                нужные визуальные функции на одном кадре.
            </p>

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
                    onClick={upload}
                    disabled={!file || loading !== ""}
                >
                    {loading === "upload"
                        ? "Загружаю…"
                        : "Загрузить видео"}
                </button>
            </div>

            {lab && (
                <div className="dev-card">
                    <p className="muted">
                        {lab.filename}
                        {" · "}
                        {lab.duration.toFixed(2)} с
                    </p>

                    <div className="dev-form-grid">
                        <label className="dev-field">
                            Таймкод, с
                            <input
                                type="number"
                                min="0"
                                max={lab.duration}
                                step="0.1"
                                value={timestamp}
                                onChange={(event) => setTimestamp(
                                    event.target.value,
                                )}
                            />
                        </label>
                    </div>

                    <div className="insight-chips">
                        {FUNCTIONS.map((item) => (
                            <label
                                key={item.id}
                                className="insight-chip"
                            >
                                <input
                                    type="checkbox"
                                    checked={selected.includes(item.id)}
                                    onChange={() => toggleFunction(item.id)}
                                />
                                {item.label}
                            </label>
                        ))}
                    </div>

                    <div className="dev-toolbar">
                        <button
                            className="primary"
                            onClick={analyze}
                            disabled={loading !== ""}
                        >
                            {loading === "analyze"
                                ? "Считаю…"
                                : "Запустить анализ"}
                        </button>
                    </div>

                    <img
                        className="dev-bev"
                        src={
                            `/api/dev/video-lab/${lab.id}/frame`
                            + `?timestamp=${timestamp}`
                        }
                        alt="Кадр"
                    />
                </div>
            )}

            {error && <div className="error">{error}</div>}

            {result && (
                <div className="dev-card">
                    <h3>Результат</h3>

                    {result.errors?.length > 0 && (
                        <ul className="insight-list">
                            {result.errors.map((item, index) => (
                                <li key={index}>
                                    <strong>{item.function}</strong>
                                    {": "}
                                    {item.error}
                                </li>
                            ))}
                        </ul>
                    )}

                    <pre className="dev-pre">
                        {JSON.stringify(result, null, 2)}
                    </pre>
                </div>
            )}
        </section>
    );
}
