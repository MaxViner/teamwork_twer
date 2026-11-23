import { useEffect, useRef, useState } from "react";
import {
    fetchJob,
    fetchJobStatus,
} from "../api/jobs.js";


const TERMINAL = new Set([
    "completed",
    "partial",
    "failed",
]);


export function useJobPolling({
    jobId,
    onError,
    intervalMs = 1500,
}) {
    const [job, setJob] = useState(null);
    const currentId = useRef(jobId);
    const generation = useRef(0);

    currentId.current = jobId;


    useEffect(() => {
        generation.current += 1;

        const token = generation.current;
        const controller = new AbortController();


        if (!jobId) {
            setJob(null);
            return undefined;
        }


        let timer;
        let stopped = false;
        let revision = null;


        setJob(null);


        const poll = async () => {
            try {
                const status = await fetchJobStatus(
                    jobId,
                    { signal: controller.signal },
                );


                if (
                    stopped
                    || generation.current !== token
                    || currentId.current !== jobId
                ) {
                    return;
                }


                const nextRevision = JSON.stringify([
                    status.status,
                    Object.entries(status.stages || {}).map((
                        [name, stage]
                    ) => [
                        name,
                        stage.status,
                        stage.result_run_id,
                    ]),
                ]);


                if (revision !== nextRevision) {
                    const shouldLoadFullJob = (
                        status.stages?.prepare?.status
                        === "completed"
                        && status.status !== "failed"
                    );


                    const data = shouldLoadFullJob
                        ? await fetchJob(
                            jobId,
                            { signal: controller.signal },
                        )
                        : {
                            ...status,
                            stages: Object.fromEntries(
                                Object.entries(
                                    status.stages || {}
                                ).map(([name, stage]) => [
                                    name,
                                    {
                                        ...stage,
                                        result: {},
                                        observations: [],
                                        history_count: 0,
                                    },
                                ]),
                            ),
                        };


                    if (
                        stopped
                        || generation.current !== token
                        || currentId.current !== jobId
                    ) {
                        return;
                    }


                    revision = nextRevision;
                    setJob(data);


                } else {
                    setJob((previous) => {
                        if (!previous) {
                            return previous;
                        }


                        const progressChanged = (
                            previous.progress
                            !== status.progress
                        );


                        const stageProgressChanged = (
                            JSON.stringify(
                                previous.stage_progress,
                            )
                            !== JSON.stringify(
                                status.stage_progress,
                            )
                        );


                        if (
                            !progressChanged
                            && !stageProgressChanged
                        ) {
                            return previous;
                        }


                        return {
                            ...previous,
                            status: status.status,
                            progress: status.progress,
                            stage_progress:
                                status.stage_progress,
                        };
                    });
                }


                if (!TERMINAL.has(status.status)) {
                    timer = setTimeout(
                        poll,
                        intervalMs,
                    );
                }


            } catch (error) {
                if (
                    stopped
                    || generation.current !== token
                    || currentId.current !== jobId
                ) {
                    return;
                }


                if (error.name === "AbortError") {
                    return;
                }


                onError(error.message);
                timer = setTimeout(
                    poll,
                    Math.max(intervalMs, 5000),
                );
            }
        };


        poll();


        return () => {
            stopped = true;
            clearTimeout(timer);
            controller.abort();
        };


    }, [jobId, onError, intervalMs]);


    const refresh = async () => {
        if (!jobId) {
            return;
        }


        const token = generation.current;
        const controller = new AbortController();


        try {
            const data = await fetchJob(
                jobId,
                { signal: controller.signal },
            );


            if (
                generation.current === token
                && currentId.current === jobId
            ) {
                setJob(data);
            }


        } finally {
            controller.abort();
        }
    };


    return {
        job,
        refresh,
    };
}