import { useCallback, useMemo, useState } from "react";
import ErrorBanner from "./components/ui/ErrorBanner.jsx";
import UploadPanel from "./components/UploadPanel.jsx";
import JobsPanel from "./components/JobsPanel.jsx";
import StageGrid from "./components/StageGrid.jsx";
import VideoWorkspace from "./components/VideoWorkspace.jsx";
import FindingsPanel from "./components/FindingsPanel.jsx";
import { useJobs } from "./hooks/useJobs.js";
import { useJobPolling } from "./hooks/useJobPolling.js";
import { useVideoPlayer } from "./hooks/useVideoPlayer.js";
import { retryJobStage, updateObservation } from "./api/jobs.js";

const ACTIVE = ["queued", "running"];

export default function App() {
  const [error, setError] = useState("");
  const [sourceFilter, setSourceFilter] = useState("all");
  const [reviewFilter, setReviewFilter] = useState("all");
  const [search, setSearch] = useState("");
  const onError = useCallback((message) => setError(message), []);

  const { jobs, selectedId, setSelectedId, uploading, upload, remove, loadJobs } = useJobs({ onError });
  const { job, refresh } = useJobPolling({ jobId: selectedId, onError });
  const { videoRef, currentTime, seek, handleTimeUpdate } = useVideoPlayer();
  const busy = ACTIVE.includes(job?.status);

  const observations = useMemo(() => Object.values(job?.stages || {}).flatMap((stage) => stage.observations || []).sort((a, b) => a.start - b.start), [job]);

  const visible = useMemo(() => observations.filter((item) => {
    const text = (item.corrected_text ?? item.text).toLowerCase();
    return (sourceFilter === "all" || item.source === sourceFilter) && (reviewFilter === "all" || item.review === reviewFilter) && text.includes(search.toLowerCase());
  }), [observations, sourceFilter, reviewFilter, search]);

  const handleUpload = async ({ file, options }) => {
    setError("");
    try { await upload({ file, options }); } catch (e) { onError(e.message); }
  };

  const handleRetry = async (stage) => {
    if (!window.confirm("Повторить этап? Текущие находки и исправления останутся в истории.")) return;
    setError("");
    try { await retryJobStage(selectedId, stage); await refresh(); } catch (e) { onError(e.message); }
  };

  const handleRemove = async () => {
    if (!window.confirm("Удалить исходное видео, результаты и всю историю этого задания?")) return;
    try { await remove(selectedId); } catch (e) { onError(e.message); }
  };

  const handleSave = async (observationId, payload) => {
    await updateObservation(selectedId, observationId, payload);
    await refresh();
  };

  return (
    <main className="app">
      <header className="page-header">
        <div><p className="eyebrow">ЛОКАЛЬНЫЙ АНАЛИЗ ВИДЕО</p><h1>Находки и свидетельства</h1></div>
        <span className="privacy">Без внешних API</span>
      </header>

      <ErrorBanner message={error} onClose={() => setError("")} />
      <UploadPanel uploading={uploading} onUpload={handleUpload} />

      <JobsPanel jobs={jobs} selectedId={selectedId} onSelect={setSelectedId} onRefresh={() => loadJobs().catch((e) => onError(e.message))} />

      {job && (
        <>
          <section className="panel">
            <div className="section-row">
              <div><h2>{job.name}</h2><p className="muted">{job.status} · {job.progress}</p></div>
              <div className="toolbar">
                    {!busy && (
                      <a
                        className="button-link"
                        href={`/api/jobs/${job.id}/report`}
                      >
                        Скачать отчёт.md
                      </a>
                    )}

                    <a
                      className="button-link"
                      href={`/api/jobs/${job.id}/export`}
                    >
                      Экспорт JSON
                    </a>

                    <button
                      className="danger"
                      disabled={busy}
                      onClick={handleRemove}
                    >
                      Удалить
                    </button>
                  </div>
            </div>
            <StageGrid job={job} busy={busy} onRetry={handleRetry} />
          </section>

          <div className="workspace">
            <VideoWorkspace job={job} observations={observations} currentTime={currentTime} videoRef={videoRef} onSeek={seek} onTimeUpdate={handleTimeUpdate} />
            <FindingsPanel observations={visible} jobId={job.id} busy={busy} search={search} onSearchChange={setSearch} sourceFilter={sourceFilter} onSourceFilterChange={setSourceFilter} reviewFilter={reviewFilter} onReviewFilterChange={setReviewFilter} onSeek={seek} onSave={handleSave} onError={onError} />
          </div>
        </>
      )}
    </main>
  );
}
