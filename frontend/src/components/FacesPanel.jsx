import { useEffect, useState } from "react";
import { fileUrl } from "../utils/fileUrl.js";
import { formatTime } from "../utils/formatTime.js";


const PEOPLE_PER_PAGE = 8;


function facesResult(job) {
    return job?.stages?.faces?.result || {};
}


function PersonCard({ job, person, onSeek }) {
    const best = person.best_frame || {};
    const box = Array.isArray(best.bbox) ? best.bbox : null;

    return (
        <article className="faces-card">
            <button
                className="faces-media"
                onClick={() => onSeek(person.first_start)}
                title="Перейти к первому появлению"
            >
                {best.artifact ? (
                    <img
                        src={fileUrl(job.id, best.artifact)}
                        alt={person.label || "Человек"}
                        loading="lazy"
                    />
                ) : (
                    <span className="faces-placeholder" />
                )}

                {box && box.length === 4 && (
                    <span
                        className="faces-box"
                        style={{
                            left: `${Math.max(0, Math.min(1, box[0])) * 100}%`,
                            top: `${Math.max(0, Math.min(1, box[1])) * 100}%`,
                            width: `${Math.max(0, Math.min(1, box[2] - box[0])) * 100}%`,
                            height: `${Math.max(0, Math.min(1, box[3] - box[1])) * 100}%`,
                        }}
                    />
                )}

                <span className="kf-frame-time">
                    {formatTime(best.timestamp ?? person.first_start)}
                </span>
            </button>

            <div className="faces-body">
                <strong>{person.label || "Человек"}</strong>
                <span className="muted">
                    {person.frame_count || 0} кадр. · с{" "}
                    {formatTime(person.first_start)}
                </span>

                {Array.isArray(person.timestamps) && person.timestamps.length > 0 && (
                    <div className="faces-times">
                        {person.timestamps.slice(0, 4).map((moment) => (
                            <button
                                className="insight-time"
                                key={moment}
                                onClick={() => onSeek(moment)}
                            >
                                {formatTime(moment)}
                            </button>
                        ))}
                    </div>
                )}
            </div>
        </article>
    );
}


export default function FacesPanel({ job, onSeek }) {
    const result = facesResult(job);
    const people = Array.isArray(result.people) ? result.people : [];

    const [page, setPage] = useState(1);

    useEffect(() => {
        setPage(1);
    }, [job?.id]);

    if (!people.length) {
        return null;
    }

    const pages = Math.max(1, Math.ceil(people.length / PEOPLE_PER_PAGE));
    const current = Math.min(page, pages);
    const visible = people.slice(
        (current - 1) * PEOPLE_PER_PAGE,
        current * PEOPLE_PER_PAGE,
    );

    return (
        <section className="panel insight-panel faces-panel">
            <div className="section-row">
                <div>
                    <h2>Люди в кадре</h2>
                    <p className="muted">
                        Анонимные метки «Человек N» объединяют похожие
                        лица внутри ролика. Личность не устанавливается.
                    </p>
                </div>

                <span className="insight-count">
                    {people.length} человек
                </span>
            </div>

            <div className="faces-grid">
                {visible.map((person) => (
                    <PersonCard
                        key={person.label}
                        job={job}
                        person={person}
                        onSeek={onSeek}
                    />
                ))}
            </div>

            {pages > 1 && (
                <div className="insight-pager">
                    <button
                        className="insight-page-button"
                        disabled={current <= 1}
                        onClick={() => setPage(current - 1)}
                    >
                        ←
                    </button>

                    <span className="muted">
                        {current} / {pages}
                    </span>

                    <button
                        className="insight-page-button"
                        disabled={current >= pages}
                        onClick={() => setPage(current + 1)}
                    >
                        →
                    </button>
                </div>
            )}
        </section>
    );
}
