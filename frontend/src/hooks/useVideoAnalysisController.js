import { useCallback, useMemo, useState } from "react";
import { COMBINED_SOURCES } from "../constants/labels.js";
import { retryJobStage, updateObservation } from "../api/jobs.js";
import { useJobs } from "./useJobs.js";
import { useJobPolling } from "./useJobPolling.js";
import { useVideoPlayer } from "./useVideoPlayer.js";

const ACTIVE = ["queued", "running"];

function allObservations(job) {
    return Object.values(job?.stages || {})
        .flatMap((stage) => stage.observations || [])
        .sort((a, b) => a.start - b.start);
}

function filterObservations(observations, { sourceFilter, reviewFilter, search }) {
    const needle = search.toLowerCase();

    return observations.filter((item) => {
        if (COMBINED_SOURCES.includes(item.source)) {
            return false;
        }

        const text = (item.corrected_text ?? item.text).toLowerCase();

        return (
            (sourceFilter === "all" || item.source === sourceFilter)
            && (reviewFilter === "all" || item.review === reviewFilter)
            && text.includes(needle)
        );
    });
}

export function useVideoAnalysisController() {
    const [error, setError] = useState("");
    const [sourceFilter, setSourceFilter] = useState("all");
    const [reviewFilter, setReviewFilter] = useState("all");
    const [search, setSearch] = useState("");
    const [uploadPanelKey, setUploadPanelKey] = useState(0);

    const onError = useCallback(
        (message) => setError(message),
        [],
    );

    const jobsState = useJobs({ onError });
    const { job, refresh } = useJobPolling({
        jobId: jobsState.selectedId,
        onError,
    });
    const video = useVideoPlayer();

    const busy = ACTIVE.includes(job?.status);

    const observations = useMemo(
        () => allObservations(job),
        [job],
    );

    const visible = useMemo(
        () => filterObservations(observations, { sourceFilter, reviewFilter, search }),
        [observations, sourceFilter, reviewFilter, search],
    );

    const handleUpload = async ({ file, options }) => {
        setError("");

        try {
            await jobsState.upload({ file, options });
        } catch (error) {
            onError(error.message);
        }
    };

    const handleRetry = async (stage) => {
        if (!window.confirm("Повторить этап? Текущие находки и исправления останутся в истории.")) {
            return;
        }

        setError("");

        try {
            await retryJobStage(jobsState.selectedId, stage);
            await refresh();
        } catch (error) {
            onError(error.message);
        }
    };

    const handleRemove = async () => {
        if (!jobsState.selectedId) {
            return;
        }

        if (!window.confirm("Удалить исходное видео, результаты, отчёт и всю историю этого задания?")) {
            return;
        }

        setError("");

        try {
            await jobsState.remove(jobsState.selectedId);
            jobsState.setSelectedId(null);
            setUploadPanelKey((current) => current + 1);
            await jobsState.loadJobs();
        } catch (error) {
            onError(error.message);
        }
    };

    const handleSave = async (observationId, payload) => {
        await updateObservation(jobsState.selectedId, observationId, payload);
        await refresh();
    };

    const handleRefreshJobs = () => jobsState.loadJobs().catch(
        (error) => onError(error.message),
    );

    return {
        error,
        clearError: () => setError(""),
        onError,
        job,
        busy,
        jobs: jobsState.jobs,
        selectedId: jobsState.selectedId,
        setSelectedId: jobsState.setSelectedId,
        uploadPanelKey,
        uploading: jobsState.uploading,
        uploadProgress: jobsState.uploadProgress,
        preparing: jobsState.preparing,
        prepareProgress: jobsState.prepareProgress,
        prepareMessage: jobsState.prepareMessage,
        observations,
        visible,
        video,
        filters: {
            sourceFilter,
            setSourceFilter,
            reviewFilter,
            setReviewFilter,
            search,
            setSearch,
        },
        actions: {
            handleUpload,
            handleRetry,
            handleRemove,
            handleSave,
            handleRefreshJobs,
        },
    };
}
