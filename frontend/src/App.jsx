import { useCallback, useMemo, useState } from "react";
import ErrorBanner from "./components/ui/ErrorBanner.jsx";
import UploadPanel from "./components/ui/uploadPanel/UploadPanel.jsx";
import JobsPanel from "./components/JobsPanel.jsx";
import StageGrid from "./components/StageGrid.jsx";
import VideoWorkspace from "./components/VideoWorkspace.jsx";
import FindingsPanel from "./components/FindingsPanel.jsx";
import LocationDossier from "./components/LocationDossier.jsx";
import { useJobs } from "./hooks/useJobs.js";
import { useJobPolling } from "./hooks/useJobPolling.js";
import { useVideoPlayer } from "./hooks/useVideoPlayer.js";
import { retryJobStage, updateObservation } from "./api/jobs.js";


const ACTIVE = ["queued", "running"];



export default function App() {
    const [error, setError] = useState("");

    const [sourceFilter, setSourceFilter] = useState(
        "all",
    );

    const [reviewFilter, setReviewFilter] = useState(
        "all",
    );

    const [search, setSearch] = useState("");

    const [uploadPanelKey, setUploadPanelKey] = useState(
        0,
    );



    const onError = useCallback(
        (message) => setError(message),
        [],
    );



    const {
        jobs,
        selectedId,
        setSelectedId,
        uploading,
        upload,
        remove,
        loadJobs,
    } = useJobs({
        onError,
    });


    const {
        job,
        refresh,
    } = useJobPolling({
        jobId: selectedId,
        onError,
    });


    const {
        videoRef,
        currentTime,
        seek,
        handleTimeUpdate,
    } = useVideoPlayer();


    const busy = ACTIVE.includes(job?.status);



    const observations = useMemo(
        () => Object.values(job?.stages || {})
            .flatMap(
                (stage) => stage.observations || [],
            )
            .sort(
                (a, b) => a.start - b.start,
            ),
        [job],
    );



    const visible = useMemo(
        () => observations.filter((item) => {
            const text = (
                item.corrected_text ?? item.text
            ).toLowerCase();


            return (
                (
                    sourceFilter === "all"
                    || item.source === sourceFilter
                )
                && (
                    reviewFilter === "all"
                    || item.review === reviewFilter
                )
                && text.includes(
                    search.toLowerCase(),
                )
            );
        }),
        [
            observations,
            sourceFilter,
            reviewFilter,
            search,
        ],
    );



    const handleUpload = async ({
        file,
        options,
    }) => {
        setError("");

        try {
            await upload({
                file,
                options,
            });

        } catch (error) {
            onError(error.message);
        }
    };



    const handleRetry = async (stage) => {
        if (
            !window.confirm(
                "Повторить этап? Текущие находки и исправления останутся в истории.",
            )
        ) {
            return;
        }


        setError("");

        try {
            await retryJobStage(
                selectedId,
                stage,
            );

            await refresh();

        } catch (error) {
            onError(error.message);
        }
    };



    const handleRemove = async () => {
        if (!selectedId) {
            return;
        }


        if (
            !window.confirm(
                "Удалить исходное видео, результаты, отчёт "
                + "и всю историю этого задания?",
            )
        ) {
            return;
        }


        setError("");

        try {
            await remove(selectedId);

            setSelectedId(null);

            setUploadPanelKey(
                (current) => current + 1,
            );

            await loadJobs();

        } catch (error) {
            onError(error.message);
        }
    };



    const handleSave = async (
        observationId,
        payload,
    ) => {
        await updateObservation(
            selectedId,
            observationId,
            payload,
        );

        await refresh();
    };



    return (
        <main className="app">
            <header className="page-header">
                <div>
                    <p className="eyebrow">
                        АНАЛИЗ ВИДЕО
                    </p>


                    <h1>
                        видеоанализатор
                    </h1>
                </div>
            </header>


            <ErrorBanner
                message={error}
                onClose={() => setError("")}
            />


            <UploadPanel
                key={uploadPanelKey}
                uploading={uploading}
                onUpload={handleUpload}
            />


            <JobsPanel
                jobs={jobs}
                selectedId={selectedId}
                job={job}
                onSelect={setSelectedId}
                onRefresh={() => loadJobs().catch(
                    (error) => onError(error.message),
                )}
            />


            {job && (
                <>
                    <section className="panel">
                        <div className="section-row">
                            <div>
                                <h2>
                                    {job.name}
                                </h2>


                                <p className="muted">
                                    {job.status}
                                    {" · "}
                                    {job.progress}
                                </p>
                            </div>


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


                        <StageGrid
                            job={job}
                            busy={busy}
                            onRetry={handleRetry}
                        />
                    </section>


                    <LocationDossier job={job} />


                    <div className="workspace">
                        <VideoWorkspace
                            job={job}
                            observations={observations}
                            currentTime={currentTime}
                            videoRef={videoRef}
                            onSeek={seek}
                            onTimeUpdate={
                                handleTimeUpdate
                            }
                        />


                        <FindingsPanel
                            observations={visible}
                            jobId={job.id}
                            busy={busy}
                            search={search}
                            onSearchChange={setSearch}
                            sourceFilter={sourceFilter}
                            onSourceFilterChange={
                                setSourceFilter
                            }
                            reviewFilter={reviewFilter}
                            onReviewFilterChange={
                                setReviewFilter
                            }
                            onSeek={seek}
                            onSave={handleSave}
                            onError={onError}
                        />
                    </div>
                </>
            )}
        </main>
    );
}