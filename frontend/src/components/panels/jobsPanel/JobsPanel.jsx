import Button from "../../ui/Button.jsx";
import CollapsiblePanel from "../../ui/CollapsiblePanel.jsx";
import "./jobsPanel.css";


const STATUS_LABELS = {
    created: "создано",
    queued: "в очереди",
    running: "выполняется",
    paused: "пауза",
    completed: "готово",
    partial: "частично",
    failed: "ошибка",
};


const ACTIVE = new Set(["queued", "running"]);


function statusOf(item, selectedJob) {
    if (selectedJob?.id === item.id) {
        return selectedJob.status || item.status;
    }

    return item.status;
}


function progressOf(item, selectedJob) {
    if (selectedJob?.id === item.id) {
        return selectedJob.progress || item.progress;
    }

    return item.progress;
}


function formatDate(value) {
    if (!value) return "";

    try {
        return new Date(value).toLocaleString();
    } catch {
        return value;
    }
}


export default function JobsPanel({
    jobs,
    selectedId,
    job,
    busy,
    onSelect,
    onRefresh,
    onDelete,
    onPause,
    onResume,
}) {
    return (
        <CollapsiblePanel
            title="Задания"
            subtitle="Выберите видео, чтобы открыть его анализ."
            actions={<Button onClick={onRefresh}>Обновить список</Button>}
        >
            {jobs.length === 0 && (
                <p className="muted">
                    Пока нет заданий. Загрузите видео выше.
                </p>
            )}

            <div className="jobs-list">
                {jobs.map((item) => {
                    const status = statusOf(item, job);
                    const active = ACTIVE.has(status);
                    const paused = status === "paused";
                    const selected = item.id === selectedId;

                    return (
                        <article
                            key={item.id}
                            className={`job-card ${selected ? "is-selected" : ""}`}
                            onClick={() => onSelect(item.id)}
                        >
                            <div className="job-card-main">
                                <div className="job-card-title">
                                    <strong>{item.name}</strong>
                                    <span className={`job-status job-status-${status || "unknown"}`}>
                                        {STATUS_LABELS[status] || status || "—"}
                                    </span>
                                </div>

                                <p className="muted job-card-meta">
                                    {formatDate(item.created_at)}
                                    {progressOf(item, job)
                                        ? ` · ${progressOf(item, job)}`
                                        : ""}
                                </p>
                            </div>

                            <div className="job-card-actions">
                                {active && (
                                    <button
                                        type="button"
                                        className="job-action"
                                        onClick={(event) => {
                                            event.stopPropagation();
                                            onPause(item.id);
                                        }}
                                    >
                                        Пауза
                                    </button>
                                )}

                                {paused && (
                                    <button
                                        type="button"
                                        className="job-action"
                                        onClick={(event) => {
                                            event.stopPropagation();
                                            onResume(item.id);
                                        }}
                                    >
                                        Продолжить
                                    </button>
                                )}

                                <button
                                    type="button"
                                    className="job-action job-action-danger"
                                    onClick={(event) => {
                                        event.stopPropagation();
                                        onDelete(item.id);
                                    }}
                                >
                                    Удалить
                                </button>
                            </div>
                        </article>
                    );
                })}
            </div>
        </CollapsiblePanel>
    );
}
