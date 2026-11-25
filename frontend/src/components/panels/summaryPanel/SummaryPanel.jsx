import { formatTime } from "../../../utils/formatTime.js";


export default function SummaryPanel({ job, onSeek }) {
    const result = job?.stages?.summary?.result;

    if (!result?.overview) {
        return null;
    }

    const topics = Array.isArray(result.topics) ? result.topics : [];
    const theses = Array.isArray(result.theses) ? result.theses : [];
    const conclusions = Array.isArray(result.conclusions) ? result.conclusions : [];

    return (
        <section className="panel insight-panel">
            <div className="section-row">
                <div>
                    <h2>Конспект</h2>
                    <p className="muted">
                        Темы, тезисы и выводы по расшифровке,
                        надписям и объектам.
                    </p>
                </div>
            </div>

            <p className="insight-overview">{result.overview}</p>

            {topics.length > 0 && (
                <div className="insight-chips">
                    {topics.slice(0, 12).map((item) => (
                        <span className="insight-chip" key={item.word}>
                            {item.word}
                            <small>{item.count}</small>
                        </span>
                    ))}
                </div>
            )}

            {theses.length > 0 && (
                <div className="insight-block">
                    <h3>Тезисы</h3>

                    <ul className="insight-list">
                        {theses.slice(0, 8).map((item) => (
                            <li key={`${item.start}-${item.text.slice(0, 24)}`}>
                                <button
                                    className="insight-time"
                                    onClick={() => onSeek(item.start)}
                                >
                                    {formatTime(item.start)}
                                </button>
                                {item.text}
                            </li>
                        ))}
                    </ul>
                </div>
            )}

            {conclusions.length > 0 && (
                <div className="insight-block">
                    <h3>Выводы</h3>

                    <ul className="insight-list">
                        {conclusions.map((item) => (
                            <li key={`${item.start}-${item.text.slice(0, 24)}`}>
                                <button
                                    className="insight-time"
                                    onClick={() => onSeek(item.start)}
                                >
                                    {formatTime(item.start)}
                                </button>
                                {item.text}
                            </li>
                        ))}
                    </ul>
                </div>
            )}
        </section>
    );
}
