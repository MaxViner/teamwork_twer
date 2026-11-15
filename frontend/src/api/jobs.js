import { request } from "./client.js";

export const fetchJobs = () => request("/jobs");
export const fetchJob = (id) => request(`/jobs/${id}`);

export function createJob({ file, options }) {
  const body = new FormData();
  body.append("file", file);
  body.append("options", JSON.stringify(options));
  return request("/jobs", { method: "POST", body });
}

export const retryJobStage = (id, stage) => request(`/jobs/${id}/retry/${stage}`, { method: "POST" });
export const deleteJob = (id) => request(`/jobs/${id}`, { method: "DELETE" });

export function updateObservation(jobId, observationId, payload) {
  return request(`/jobs/${jobId}/observations/${observationId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
}
