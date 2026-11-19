import { useCallback, useEffect, useState } from "react";
import {
    createJob,
    deleteJob,
    fetchJob,
    fetchJobs,
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


const PREPARE_POLL_MS = 800;

const PREPARE_MAX_ERRORS = 10;



function wait(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}



function prepareState(job) {
    const stage = job?.stages?.prepare || {};

    const percent = (
        job?.stage_progress?.prepare
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
            || job?.progress
            || ""
        ),
        stageStatus: stage.status || "",
        jobStatus: job?.status || "",
    };
}



async function followPreparation(jobId, onUpdate) {
    let errors = 0;


    while (true) {
        let job;

        try {
            job = await fetchJob(jobId);

            errors = 0;

        } catch (error) {
            errors += 1;


            if (errors >= PREPARE_MAX_ERRORS) {
                throw error;
            }


            await wait(PREPARE_POLL_MS);

            continue;
        }


        const state = prepareState(job);

        onUpdate(state);


        if (
            PREPARE_DONE.includes(state.stageStatus)
            || JOB_DONE.includes(state.jobStatus)
        ) {
            return job;
        }


        await wait(PREPARE_POLL_MS);
    }
}



export function useJobs({ onError }) {
    const [jobs, setJobs] = useState([]);

    const [selectedId, setSelectedId] = useState("");

    const [uploading, setUploading] = useState(false);

    const [uploadProgress, setUploadProgress] = useState(null);

    const [preparing, setPreparing] = useState(false);

    const [prepareProgress, setPrepareProgress] = useState(null);

    const [prepareMessage, setPrepareMessage] = useState("");



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
            setPrepareMessage("Задание создано, жду начала подготовки");

            try {
                await followPreparation(
                    result.id,
                    (state) => {
                        setPrepareProgress(state.percent);

                        if (state.message) {
                            setPrepareMessage(state.message);
                        }
                    },
                );

            } finally {
                setPreparing(false);
                setPrepareProgress(null);
                setPrepareMessage("");
            }

            return result;

        } finally {
            setUploading(false);
            setUploadProgress(null);

            setPreparing(false);
            setPrepareProgress(null);
            setPrepareMessage("");
        }

    }, [loadJobs]);



    const remove = useCallback(async (jobId) => {
        await deleteJob(jobId);

        await loadJobs();

        setSelectedId("");

    }, [loadJobs]);



    useEffect(() => {
        loadJobs()
            .then((items) => {
                if (items.length) {
                    setSelectedId(items[0].id);
                }
            })
            .catch((error) => onError(error.message));

    }, [loadJobs, onError]);



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
        loadJobs,
    };
}