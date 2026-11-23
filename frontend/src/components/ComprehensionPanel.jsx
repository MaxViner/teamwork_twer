import { useEffect, useState } from "react";
import { formatTime } from "../utils/formatTime.js";


const KIND_LABELS = {
    overview: "Обзор",
    section: "Раздел",
    fact: "Факт",
    places: "Места",
    number: "Число",
    objects: "Объекты",
    structure: "Структура",
};


export default function ComprehensionPanel({ job, onSeek }) {
    const result = job?.stages?.comprehension?.result;
    const questions = Array.isArray(result?.questions)
        ? result.questions.filter((item) => item.kind !== "structure")
        : [];
    const [open, setOpen] = useState({});

    useEffect(() => {
        setOpen({});
    }, [job?.id]);

    if (!questions.length) {
        return null;
    }

    const toggle = (index) => {
        setOpen((current) => ({
            ...current,
            [index]: !current[index],
        }));
    };

    return (
        <section className="panel comprehension-panel">
            <div className="section-row">
                <div>
                    <h2>Проверка понимания</h2>
                    <p className="muted">
                        Вопросы по фактическому содержанию видео.
                        Откройте, чтобы увидеть ответ.
                    </p>
                </div>

                <span className="insight-count">
                    {questions.length} вопрос.
                </span>
            </div>

            <div className="comprehension-list">
                {questions.map((item, index) => (
                    <div
                        className={`comprehension-item${open[index] ? " is-open" : ""}`}
                        key={`${item.kind}-${index}`}
                    >
                        <div className="comprehension-head">
                            <button
                                className="comprehension-question"
                                onClick={() => toggle(index)}
                            >
                                <span className="comprehension-mark">
                                    {open[index] ? "−" : "+"}
                                </span>
                                {item.question}
                            </button>

                            <div className="comprehension-meta">
                                <span className="insight-chip">
                                    {KIND_LABELS[item.kind] || item.kind}
                                </span>

                                {item.time_seconds !== null && item.time_seconds !== undefined && (
                                    <button
                                        className="insight-time"
                                        onClick={() => onSeek(item.time_seconds)}
                                    >
                                        {formatTime(item.time_seconds)}
                                    </button>
                                )}
                            </div>
                        </div>

                        {open[index] && (
                            <p className="comprehension-answer">
                                {item.answer}
                            </p>
                        )}
                    </div>
                ))}
            </div>
        </section>
    );
}
