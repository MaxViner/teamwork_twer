import Button from "../ui/Button.jsx";


const CONFIDENCE_LABELS = {
    low: "низкая",
    medium: "средняя",
    high: "высокая",
};


function Chips({ items }) {
    if (!items?.length) {
        return null;
    }

    return (
        <div className="ai-description__chips">
            {items.map((item) => (
                <span className="ai-description__chip" key={item}>
                    {item}
                </span>
            ))}
        </div>
    );
}


export default function AiDescription({
    description,
    loading,
    error,
    configured,
    hint,
    onRequest,
}) {
    const disabled = loading || configured === false;
    const hasDescription = Boolean(
        description?.summary
        || description?.identification,
    );

    return (
        <div className="ai-description">
            <div className="ai-description__actions">
                <Button
                    onClick={() => onRequest(Boolean(hasDescription))}
                    disabled={disabled}
                >
                    {loading
                        ? "AI анализирует…"
                        : hasDescription
                            ? "Обновить AI описание"
                            : "Получить AI описание"}
                </Button>

                {description?.model && (
                    <span className="ai-description__meta">
                        {description.provider} · {description.model}
                    </span>
                )}
            </div>

            {error && (
                <p className="ai-description__error">{error}</p>
            )}

            {!error && configured === false && (
                <p className="muted ai-description__hint">
                    {hint}
                </p>
            )}

            {hasDescription && (
                <div className="ai-description__body">
                    {description.identification && (
                        <p className="ai-description__identification">
                            <span>Похоже на:</span>{" "}
                            {description.identification}
                        </p>
                    )}

                    {description.summary && (
                        <p className="ai-description__summary">
                            {description.summary}
                        </p>
                    )}

                    {description.features?.length > 0 && (
                        <div className="ai-description__block">
                            <h4>Признаки</h4>
                            <Chips items={description.features} />
                        </div>
                    )}

                    {description.place_hypotheses?.length > 0 && (
                        <div className="ai-description__block">
                            <h4>Гипотезы о месте</h4>
                            <ul className="ai-description__hypotheses">
                                {description.place_hypotheses.map((item) => (
                                    <li key={`${item.place}-${item.reason}`}>
                                        <strong>{item.place}</strong>
                                        <span className="ai-description__confidence">
                                            {CONFIDENCE_LABELS[item.confidence] || item.confidence}
                                        </span>
                                        {item.reason && (
                                            <span className="muted"> — {item.reason}</span>
                                        )}
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}

                    {description.search_queries?.length > 0 && (
                        <div className="ai-description__block">
                            <h4>Поисковые запросы</h4>
                            <Chips items={description.search_queries} />
                        </div>
                    )}

                    {description.web_summary && (
                        <details className="ai-description__web">
                            <summary>Что нашлось в интернете</summary>
                            <p>{description.web_summary}</p>
                        </details>
                    )}

                    {description.sources?.length > 0 && (
                        <div className="ai-description__block">
                            <h4>Источники</h4>
                            <ul className="ai-description__sources">
                                {description.sources.map((source) => (
                                    <li key={source.url}>
                                        <a
                                            href={source.url}
                                            target="_blank"
                                            rel="noreferrer"
                                        >
                                            {source.title || source.url}
                                        </a>
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}

                    {description.caveats?.length > 0 && (
                        <div className="ai-description__block">
                            <h4>Ограничения</h4>
                            <Chips items={description.caveats} />
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
