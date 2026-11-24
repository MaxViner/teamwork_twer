import { request } from "./client.js";


export function describeImage(file, prompt = "") {
    const body = new FormData();

    body.append("file", file);
    body.append("prompt", prompt);

    return fetch("/api/dev/vision/describe", {
        method: "POST",
        body,
    }).then(async (response) => {
        const payload = await response.json().catch(() => null);

        if (!response.ok) {
            throw new Error(
                payload?.detail
                || `HTTP ${response.status}`
            );
        }

        return payload;
    });
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