import { useId, useState } from "react";


/**
 * Панель с заголовком и кнопкой «Свернуть / Развернуть».
 *
 * Сворачивание анимируется через grid-template-rows, поэтому
 * содержимое не прыгает и остаётся в DOM (важно для фильтров).
 */
export default function CollapsiblePanel({
    title,
    subtitle,
    actions,
    defaultOpen = true,
    className = "",
    children,
}) {
    const [expanded, setExpanded] = useState(defaultOpen);
    const contentId = `${useId()}-content`;

    return (
        <section className={`panel collapsible-panel ${className}`.trim()}>
            <div className="collapsible-panel__header">
                <div className="collapsible-panel__title">
                    <h2>{title}</h2>

                    {subtitle ? (
                        <p className="muted collapsible-panel__subtitle">
                            {subtitle}
                        </p>
                    ) : null}
                </div>

                <div className="collapsible-panel__actions">
                    {actions}

                    <button
                        type="button"
                        className="collapsible-panel__toggle"
                        onClick={() => setExpanded((current) => !current)}
                        aria-expanded={expanded}
                        aria-controls={contentId}
                    >
                        <span>
                            {expanded ? "Свернуть" : "Развернуть"}
                        </span>

                        <span
                            className="collapsible-panel__chevron"
                            aria-hidden="true"
                        >
                            ▾
                        </span>
                    </button>
                </div>
            </div>

            <div
                id={contentId}
                className={
                    "collapsible-panel__content"
                    + (expanded ? " is-expanded" : "")
                }
            >
                <div className="collapsible-panel__inner">
                    {children}
                </div>
            </div>
        </section>
    );
}
