// hooks/useServerKeyframes.js
import { useEffect, useState } from "react";
import { fetchKeyframes } from "../../../api/jobs.js";
import { FRAMES_PER_PAGE } from "../lib/constants.js";

// Кадры с сервера постранично. Пока задание выполняется, страница
// берёт локальные данные, чтобы не запрашивать неполный результат.
export function useServerKeyframes(
    job,
    page,
    group,
    enabled,
) {
    const jobId = job?.id;
    const [state, setState] = useState({
        data: null,
        loading: false,
        error: null,
    });

    useEffect(() => {
        if (!enabled || !jobId) {
            setState({
                data: null,
                loading: false,
                error: null,
            });
            return undefined;
        }

        let cancelled = false;

        setState((previous) => ({
            ...previous,
            loading: true,
            error: null,
        }));

        fetchKeyframes(jobId, {
            page,
            pageSize: FRAMES_PER_PAGE,
            group,
        })
            .then((data) => {
                if (cancelled) {
                    return;
                }

                setState({
                    data,
                    loading: false,
                    error: null,
                });
            })
            .catch((error) => {
                if (cancelled) {
                    return;
                }

                setState({
                    data: null,
                    loading: false,
                    error,
                });
            });

        return () => {
            cancelled = true;
        };
    }, [jobId, page, group, enabled]);

    return state;
}
