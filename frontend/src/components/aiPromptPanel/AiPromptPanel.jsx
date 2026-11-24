import { useState } from "react";
import Button from "../ui/Button.jsx";
import "./AiPromptPanel.css";


const STATUS_LABELS = {
    pending: "Этап ещё не запускался.",
    queued: "Этап в очереди.",
    running: "AI формирует поисковый промпт…",
};


export default function AiPromptPanel({ job, onRetry }) {
    const [copied, setCopied] = useState(false);

    const stage = job?.stages?.ai_prompt;

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
            <section className="panel ai-prompt-panel">
                <div className="section-row">
                    <div>
                        <h2>Поисковый промпт (AI)</h2>
                        <p className="muted">
                            Готовое задание для агента-геолокатора: собрано
                            по всем накопленным уликам. Это не найденные
                            координаты, а формулировка поиска.
                        </p>
                    </div>

                    <span className="ai-prompt-panel__badge">
                        {result.provider || "AI"}
                        {result.model ? ` · ${result.model}` : ""}
                    </span>
                </div>

                <div className="ai-prompt-panel__actions">
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
                </div>

                <pre className="ai-prompt-panel__text">{prompt}</pre>

                {result.note && (
                    <p className="muted ai-prompt-panel__note">
                        {result.note}
                    </p>
                )}
            </section>
        );
    }

    if (status === "failed") {
        return (
            <section className="panel ai-prompt-panel">
                <h2>Поисковый промпт (AI)</h2>
                <p className="ai-prompt-panel__error">
                    {stage.error || "Не удалось сформировать промпт."}
                </p>

                {onRetry && (
                    <Button onClick={() => onRetry("ai_prompt")}>
                        Повторить этап
                    </Button>
                )}
            </section>
        );
    }

    if (status === "skipped") {
        return (
            <section className="panel ai-prompt-panel">
                <h2>Поисковый промпт (AI)</h2>
                <p className="muted">
                    {stage.note || "Этап пропущен."}
                </p>

                {onRetry && (
                    <Button onClick={() => onRetry("ai_prompt")}>
                        Повторить этап
                    </Button>
                )}
            </section>
        );
    }

    return (
        <section className="panel ai-prompt-panel">
            <h2>Поисковый промпт (AI)</h2>
            <p className="muted">
                {STATUS_LABELS[status] || "Этап ещё не завершён."}
            </p>
        </section>
    );
}
