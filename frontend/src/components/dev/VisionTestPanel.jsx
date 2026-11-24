import { useRef, useState } from "react";
import { describeImage } from "../../api/dev.js";


export default function VisionTestPanel() {
    const [file, setFile] = useState(null);
    const [preview, setPreview] = useState("");
    const [prompt, setPrompt] = useState("");
    const [result, setResult] = useState(null);
    const [error, setError] = useState("");
    const [busy, setBusy] = useState(false);
    const inputRef = useRef(null);


    const handleFile = (event) => {
        const selected = event.target.files?.[0];

        if (!selected) return;

        setFile(selected);
        setPreview(URL.createObjectURL(selected));
        setResult(null);
        setError("");
    };


    const handleAnalyze = async () => {
        if (!file) {
            setError("Выберите изображение.");
            return;
        }

        setBusy(true);
        setError("");

        try {
            const data = await describeImage(file, prompt);
            setResult(data);
        } catch (err) {
            setError(err.message);
        } finally {
            setBusy(false);
        }
    };


    const analysis = result?.analysis || {};


    return (
        <section className="panel">
            <h2>Тест распознавания изображения</h2>

            <p className="muted">
                Загрузите фото, чтобы проверить функции визуального
                анализа и получить описание, объекты и признаки места.
            </p>

            <input
                ref={inputRef}
                type="file"
                accept="image/*"
                onChange={handleFile}
            />

            {preview && (
                <img
                    src={preview}
                    alt="Загруженное изображение"
                    style={{
                        maxWidth: "100%",
                        maxHeight: "420px",
                        borderRadius: "12px",
                        marginTop: "14px",
                    }}
                />
            )}

            <label>
                Дополнительный запрос
                <textarea
                    value={prompt}
                    onChange={(event) => setPrompt(event.target.value)}
                    placeholder="Например: определи вероятную страну и тип места"
                />
            </label>

            <button
                className="primary"
                disabled={busy || !file}
                onClick={handleAnalyze}
            >
                {busy ? "Анализирую…" : "Проанализировать"}
            </button>

            {error && (
                <div className="error">{error}</div>
            )}

            {analysis && (
                <div className="insight-overview">
                    <h3>Краткое описание</h3>
                    <p>{analysis.short_description}</p>

                    <h3>Подробное описание</h3>
                    <p>{analysis.detailed_description}</p>

                    {analysis.main_objects?.length > 0 && (
                        <>
                            <h3>Объекты</h3>
                            <div className="insight-chips">
                                {analysis.main_objects.map((
                                    item,
                                    index
                                ) => (
                                    <span
                                        key={index}
                                        className="insight-chip"
                                    >
                                        {item.name}
                                        <small>
                                            {Math.round(
                                                (item.confidence || 0) * 100
                                            )}%
                                        </small>
                                    </span>
                                ))}
                            </div>
                        </>
                    )}

                    {analysis.location_clues?.length > 0 && (
                        <>
                            <h3>Признаки места</h3>
                            <ul className="insight-list">
                                {analysis.location_clues.map((
                                    item,
                                    index
                                ) => (
                                    <li key={index}>{item}</li>
                                ))}
                            </ul>
                        </>
                    )}

                    {analysis.search_queries?.length > 0 && (
                        <>
                            <h3>Поисковые запросы</h3>
                            <div className="insight-chips">
                                {analysis.search_queries.map((
                                    item,
                                    index
                                ) => (
                                    <span
                                        key={index}
                                        className="insight-chip"
                                    >
                                        {item}
                                    </span>
                                ))}
                            </div>
                        </>
                    )}
                </div>
            )}
        </section>
    );
}