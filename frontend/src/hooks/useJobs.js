import { useCallback, useEffect, useState } from "react";
import {
    createJob,
    deleteJob,
    fetchJobs,
} from "../api/jobs.js";



export function useJobs({ onError }) {
    const [jobs, setJobs] = useState([]);

    const [selectedId, setSelectedId] = useState("");

    const [uploading, setUploading] = useState(false);



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

        try {
            const result = await createJob({
                file,
                options,
            });

            await loadJobs();

            setSelectedId(result.id);

            return result;

        } finally {
            setUploading(false);
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
        upload,
        remove,
        loadJobs,
    };
}