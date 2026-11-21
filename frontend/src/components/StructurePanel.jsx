import { formatTime } from "../utils/formatTime.js";


export default function StructurePanel({ job, onSeek }) {
    const sections = job?.stages?.video_structure?.result?.sections;

    if (!Array.isArray(sections) || !sections.length) {
        return null;
    }

    return (
        <section className="panel insight-panel">
            <div className="section-row">
                <div>
                    <h2>Структура видео</h2>
                    <p className="muted">
                        Смысловые разделы с таймкодами. Нажмите
                        на время, чтобы перейти к началу.
                    </p>
                </div>

                <span className="insight-count">
                    {sections.length} разд.
                </span>
            </div>

            <div className="structure-list">
                {sections.map((section) => (
                    <div className="structure-row" key={section.number}>
                        <button
                            className="insight-time"
                            onClick={() => onSeek(section.start)}
                        >
                            {formatTime(section.start)}
                        </button>

                        <div>
                            <strong>{section.title}</strong>

                            {section.summary && (
                                <p className="muted">
                                    {section.summary}
                                </p>
                            )}

                            {Array.isArray(section.keywords) && section.keywords.length > 0 && (
                                <div className="insight-chips">
                                    {section.keywords.slice(0, 6).map((word) => (
                                        <span className="insight-chip" key={word}>
                                            {word}
                                        </span>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>
                ))}
            </div>
        </section>
    );
}
