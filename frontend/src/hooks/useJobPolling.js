import { useEffect, useState } from "react";
import { fetchJob } from "../api/jobs.js";

export function useJobPolling({ jobId, onError, intervalMs = 1000 }) {
  const [job, setJob] = useState(null);

  useEffect(() => {
    if (!jobId) { setJob(null); return; }
    let stopped = false, timer;
    setJob(null);

    const poll = async () => {
      try {
        const data = await fetchJob(jobId);
        if (!stopped) setJob(data);
      } catch (error) {
        if (!stopped) onError(error.message);
      }
      if (!stopped) timer = setTimeout(poll, intervalMs);
    };

    poll();
    return () => { stopped = true; clearTimeout(timer); };
  }, [jobId, onError, intervalMs]);

  const refresh = async () => { if (jobId) setJob(await fetchJob(jobId)); };
  return { job, refresh };
}
