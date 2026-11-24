import { request } from "./client.js";


function responseError(status, body) {
    return new Error(
        typeof body?.detail === "string"
            ? body.detail
            : JSON.stringify(
                body?.detail
                || `HTTP ${status}`,
            ),
    );
}



export const fetchJobs = () =>
    request("/jobs");



export const fetchJob = (id, options = {}) =>
    request(`/jobs/${id}`, options);

export const fetchJobStatus = (id, options = {}) =>
    request(`/jobs/${id}/status`, options);


export const fetchMapQuery = (id, options = {}) =>
    request(`/jobs/${id}/map-query`, options);



export const fetchAiStatus = (options = {}) =>
    request("/ai/status", options);



export function describeObject(
    id,
    label,
    { refresh = false } = {},
) {
    const suffix = refresh ? "?refresh=true" : "";

    return request(
        `/jobs/${id}/objects/`
        + `${encodeURIComponent(label)}/ai-description`
        + suffix,
        {
            method: "POST",
        },
    );
}



export const searchJob = (id, query) =>
    request(
        `/jobs/${id}/search?q=${encodeURIComponent(query)}`,
    );



export function fetchKeyframes(
    id,
    { page = 1, pageSize = 12, group = null } = {},
) {
    const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
    });

    if (group !== null && group !== undefined) {
        params.set("group", String(group));
    }

    return request(
        `/jobs/${id}/keyframes?${params.toString()}`,
    );
}



export function fetchRoads(
    id,
    { page = 1, pageSize = 8 } = {},
) {
    return request(
        `/jobs/${id}/roads?page=${page}&page_size=${pageSize}`,
    );
}



export function createJob({
    file,
    options,
    onProgress,
}) {
    const body = new FormData();

    body.append("file", file);

    body.append(
        "options",
        JSON.stringify(options),
    );

    return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();

        xhr.open("POST", "/api/jobs");

        xhr.upload.onprogress = (event) => {
            if (
                !event.lengthComputable
                || !onProgress
            ) {
                return;
            }

            onProgress(
                Math.min(
                    100,
                    Math.round(
                        event.loaded
                        / event.total
                        * 100,
                    ),
                ),
            );
        };

        xhr.upload.onload = () => {
            onProgress?.(100);
        };

        xhr.onload = () => {
            let payload = null;

            try {
                payload = xhr.responseText
                    ? JSON.parse(xhr.responseText)
                    : null;
            } catch {
                payload = null;
            }

            if (
                xhr.status >= 200
                && xhr.status < 300
            ) {
                resolve(payload);
            } else {
                reject(
                    responseError(
                        xhr.status,
                        payload,
                    ),
                );
            }
        };

        xhr.onerror = () => reject(
            new Error(
                "Не удалось загрузить видео. "
                + "Проверьте соединение.",
            ),
        );

        xhr.onabort = () => reject(
            new Error("Загрузка отменена."),
        );

        xhr.send(body);
    });
}



export const retryJobStage = (
    id,
    stage,
) => request(
    `/jobs/${id}/retry/${stage}`,
    {
        method: "POST",
    },
);



export const deleteJob = (id) =>
    request(
        `/jobs/${id}`,
        {
            method: "DELETE",
        },
    );



export function updateObservation(
    jobId,
    observationId,
    payload,
) {
    return request(
        `/jobs/${jobId}/observations/${observationId}`,
        {
            method: "PATCH",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify(payload),
        },
    );
}