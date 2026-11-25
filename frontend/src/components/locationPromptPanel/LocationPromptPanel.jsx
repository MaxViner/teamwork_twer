import { useState } from "react";
import Button from "../ui/Button.jsx";
import "./LocationPromptPanel.css";


const STATUS_LABELS = {
    pending: "Этап ещё не запускался.",
    queued: "Этап в очереди.",
    running: "AI формирует поисковый промпт…",
};


export default function LocationPromptPanel({ job, onRetry }) {
    const [copied, setCopied] = useState(false);

    const stage = job?.stages?.location_prompt;

    if (!stage) {
        return null;
    }

    const status = stage.status;
    const result = stage.result || {};
    const prompt = typeof result.prompt === "string"
        ? result.prompt.trim()
        : "";

    if (status === "completed" && prompt) {
        return (
            <section className="panel location-prompt-panel">
                <div className="section-row">
                    <div>
                        <h2>Поисковый промпт (AI)</h2>
                        <p className="muted">
                            Готовое задание для агента-геолокатора: собрано
                            по всем накопленным уликам. Это не найденные
                            координаты, а формулировка поиска.
                        </p>
                    </div>

                    <span className="location-prompt-panel__badge">
                        {result.provider || "AI"}
                        {result.model ? ` · ${result.model}` : ""}
                    </span>
                </div>

                <div className="location-prompt-panel__actions">
                    <Button
                        onClick={async () => {
                            try {
                                await navigator.clipboard.writeText(prompt);
                                setCopied(true);
                                window.setTimeout(() => setCopied(false), 2000);
                            } catch {
                                setCopied(false);
                            }
                        }}
                    >
                        {copied ? "Скопировано" : "Скопировать промпт"}
                    </Button>

                    {result.artifact && (
                        <a
                            className="btn btn-ghost"
                            href={`/api/jobs/${job.id}/files/${result.artifact}`}
                            target="_blank"
                            rel="noreferrer"
                        >
                            Открыть location_prompt.md
                        </a>
                    )}
                </div>

                <pre className="location-prompt-panel__text">{prompt}</pre>

                {result.input && (
                    <p className="muted location-prompt-panel__note">
                        Вход: текстовых улик {result.input.text_clues ?? 0},
                        реплик {result.input.transcript_segments ?? 0},
                        ориентиров {result.input.landmarks ?? 0},
                        эпизодов дороги {result.input.road_episodes ?? 0}.
                    </p>
                )}

                {result.note && (
                    <p className="muted location-prompt-panel__note">
                        {result.note}
                    </p>
                )}
            </section>
        );
    }

    if (status === "failed") {
        return (
            <section className="panel location-prompt-panel">
                <h2>Поисковый промпт (AI)</h2>
                <p className="location-prompt-panel__error">
                    {stage.error || "Не удалось сформировать промпт."}
                </p>

                {onRetry && (
                    <Button onClick={() => onRetry("location_prompt")}>
                        Повторить этап
                    </Button>
                )}
            </section>
        );
    }

    if (status === "skipped") {
        return (
            <section className="panel location-prompt-panel">
                <h2>Поисковый промпт (AI)</h2>
                <p className="muted">
                    {stage.note || "Этап пропущен: AI-провайдер не настроен."}
                </p>

                {onRetry && (
                    <Button onClick={() => onRetry("location_prompt")}>
                        Повторить этап
                    </Button>
                )}
            </section>
        );
    }

    return (
        <section className="panel location-prompt-panel">
            <h2>Поисковый промпт (AI)</h2>
            <p className="muted">
                {STATUS_LABELS[status] || "Этап ещё не завершён."}
            </p>
        </section>
    );
}
