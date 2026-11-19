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



export const fetchJob = (id) =>
    request(`/jobs/${id}`);



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