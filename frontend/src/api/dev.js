import { request } from "./client.js";


async function postForm(path, form) {
    const response = await fetch(`/api${path}`, {
        method: "POST",
        body: form,
    });

    const payload = await response.json().catch(() => null);

    if (!response.ok) {
        throw new Error(
            typeof payload?.detail === "string"
                ? payload.detail
                : payload?.reason
                || `HTTP ${response.status}`,
        );
    }

    return payload;
}


// ── AI-описание (внешний провайдер) ─────────────────────

export function describeImage(file, prompt = "") {
    const body = new FormData();

    body.append("file", file);
    body.append("prompt", prompt);

    return postForm("/dev/vision/describe", body);
}


export function sendChat(message, options = {}) {
    return request("/dev/ai/chat", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({
            message,
            web_search: Boolean(options.webSearch),
            system: options.system || null,
        }),
    });
}


// ── Локальный визуальный анализ ─────────────────────────

export function analyzeVision(file) {
    const body = new FormData();
    body.append("file", file);

    return postForm("/test/vision", body);
}


export function analyzeGeoClues(file) {
    const body = new FormData();
    body.append("file", file);

    return postForm("/test/geo-clues", body);
}


export function fetchDevServices() {
    return request("/dev/services");
}


// ── Одометрия + BEV ─────────────────────────────────────

export function uploadOdometryVideo(file) {
    const body = new FormData();
    body.append("file", file);

    return postForm("/dev/odometry-lab/upload", body);
}


export function analyzeOdometry(labId, payload) {
    return request(`/dev/odometry-lab/${labId}/analyze`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
    });
}


export function analyzeOdometryPair(frameA, frameB) {
    const body = new FormData();
    body.append("frame_a", frameA);
    body.append("frame_b", frameB);

    return postForm("/dev/odometry-lab/pair", body);
}


export function deleteOdometryLab(labId) {
    return request(`/dev/odometry-lab/${labId}`, {
        method: "DELETE",
    });
}


// ── Карт-исследование ───────────────────────────────────

export function fetchGeoMeta() {
    return request("/geo/meta");
}


export function runGeoResearch(payload) {
    return request("/geo/research", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
    });
}
