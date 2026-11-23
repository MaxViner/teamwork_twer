import StageGrid from "../components/StageGrid.jsx";

export default function JobStatusSection({ job, busy, onRetry, onRemove }) {
    if (!job) return null;

    return (
        <section className="panel">
            <div className="section-row">
                <div>
                    <h2>{job.name}</h2>
                    <p className="muted">
                        {job.status}
                        {" · "}
                        {job.progress}
                    </p>
                </div>

                <div className="toolbar">
                    {!busy && (
                        <a className="button-link" href={`/api/jobs/${job.id}/report`}>
                            Скачать отчёт.md
                        </a>
                    )}

                    <a className="button-link" href={`/api/jobs/${job.id}/export`}>
                        Экспорт JSON
                    </a>

                    <a className="button-link" href={`/api/jobs/${job.id}/evidence`}>
                        Улики JSON
                    </a>

                    <button className="danger" disabled={busy} onClick={onRemove}>
                        Удалить
                    </button>
                </div>
            </div>

            <StageGrid job={job} busy={busy} onRetry={onRetry} />
        </section>
    );
}
