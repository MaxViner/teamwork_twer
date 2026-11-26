import { useCallback, useEffect, useRef, useState } from "react";
import {
    createJob,
    deleteJob,
    fetchJob,
    fetchJobStatus,
    fetchJobs,
    pauseJob,
    resumeJob,
} from "../api/jobs.js";


const PREPARE_DONE = [
    "completed",
    "failed",
    "skipped",
];


const JOB_DONE = [
    "completed",
    "partial",
    "failed",
];


const PREPARE_POLL_MS = 1000;
const PREPARE_MAX_ERRORS = 10;


function wait(ms, signal) {
    return new Promise((resolve, reject) => {
        if (signal?.aborted) {
            reject(new DOMException("Aborted", "AbortError"));
            return;
        }

        const onAbort = () => {
            clearTimeout(timer);
            reject(new DOMException("Aborted", "AbortError"));
        };

        const timer = setTimeout(() => {
            signal?.removeEventListener("abort", onAbort);
            resolve();
        }, ms);

        signal?.addEventListener("abort", onAbort, { once: true });
    });
}


function prepareState(status) {
    const stage = status?.stages?.prepare || {};


    const percent = (
        status?.stage_progress?.prepare
        ?? stage.progress
        ?? null
    );


    return {
        percent: percent == null
            ? null
            : Math.max(
                0,
                Math.min(100, Number(percent)),
            ),
        message: (
            stage.progress_message
            || status?.progress
            || ""
        ),
        stageStatus: stage.status || "",
        jobStatus: status?.status || "",
    };
}


async function followPreparation(
    jobId,
    onUpdate,
    signal,
) {
    let errors = 0;


    while (!signal.aborted) {
        let status;


        try {
            status = await fetchJobStatus(
                jobId,
                { signal },
            );


            errors = 0;


        } catch (error) {
            if (error.name === "AbortError") {
                throw error;
            }


            errors += 1;


            if (errors >= PREPARE_MAX_ERRORS) {
                throw error;
            }


            await wait(
                PREPARE_POLL_MS,
                signal,
            );


            continue;
        }


        const state = prepareState(status);


        onUpdate(state);


        if (
            PREPARE_DONE.includes(state.stageStatus)
            || JOB_DONE.includes(state.jobStatus)
        ) {
            return status;
        }


        await wait(
            PREPARE_POLL_MS,
            signal,
        );
    }


    throw new DOMException("Aborted", "AbortError");
}


export function useJobs({ onError }) {
    const [jobs, setJobs] = useState([]);
    const [selectedId, setSelectedId] = useState("");
    const [uploading, setUploading] = useState(false);
    const [uploadProgress, setUploadProgress] = useState(null);
    const [preparing, setPreparing] = useState(false);
    const [prepareProgress, setPrepareProgress] = useState(null);
    const [prepareMessage, setPrepareMessage] = useState("");

    const activePreparation = useRef(null);


    const loadJobs = useCallback(async () => {
        const items = await fetchJobs();
        setJobs(items);
        return items;
    }, []);


    const upload = useCallback(async ({
        file,
        options,
    }) => {
        if (!file) {
            return null;
        }


        activePreparation.current?.abort();


        const controller = new AbortController();
        activePreparation.current = controller;


        setUploading(true);
        setUploadProgress(0);
        setPreparing(false);
        setPrepareProgress(null);
        setPrepareMessage("");


        try {
            const result = await createJob({
                file,
                options,
                onProgress: setUploadProgress,
            });


            await loadJobs();
            setSelectedId(result.id);


            setUploading(false);
            setUploadProgress(null);


            setPreparing(true);
            setPrepareMessage(
                "Задание создано, жду начала подготовки",
            );


            try {
                await followPreparation(
                    result.id,
                    (state) => {
                        setPrepareProgress(state.percent);


                        if (state.message) {
                            setPrepareMessage(state.message);
                        }
                    },
                    controller.signal,
                );


            } finally {
                setPreparing(false);
                setPrepareProgress(null);
                setPrepareMessage("");
            }


            return result;


        } catch (error) {
            if (error.name !== "AbortError") {
                throw error;
            }


            return null;


        } finally {
            if (activePreparation.current === controller) {
                activePreparation.current = null;
            }


            setUploading(false);
            setUploadProgress(null);
            setPreparing(false);
            setPrepareProgress(null);
            setPrepareMessage("");
        }


    }, [loadJobs]);


    const remove = useCallback(async (jobId) => {
        activePreparation.current?.abort();
        activePreparation.current = null;


        await deleteJob(jobId);
        const items = await loadJobs();
        setSelectedId("");
        return items;
    }, [loadJobs]);


    const pause = useCallback(async (jobId) => {
        await pauseJob(jobId);
        await loadJobs();
    }, [loadJobs]);


    const resume = useCallback(async (jobId) => {
        await resumeJob(jobId);
        await loadJobs();
    }, [loadJobs]);


    useEffect(() => {
        return () => {
            activePreparation.current?.abort();
            activePreparation.current = null;
        };
    }, []);


    useEffect(() => {
        loadJobs()
            .then((items) => {
                if (items.length) {
                    setSelectedId(items[0].id);
                }
            })
            .catch((error) => onError(error.message));


    }, [loadJobs, onError]);


    useEffect(() => {
        const active = jobs.some((job) => (
            job.status === "queued"
            || job.status === "running"
        ));

        if (!active) {
            return undefined;
        }

        const timer = setInterval(() => {
            loadJobs().catch(() => {});
        }, 4000);

        return () => clearInterval(timer);
    }, [jobs, loadJobs]);


    return {
        jobs,
        selectedId,
        setSelectedId,
        uploading,
        uploadProgress,
        preparing,
        prepareProgress,
        prepareMessage,
        upload,
        remove,
        pause,
        resume,
        loadJobs,
    };
}