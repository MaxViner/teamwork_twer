export function fileUrl(jobId, path) {
  if (!path) return "";
  return `/api/jobs/${jobId}/files/${path.split("/").map(encodeURIComponent).join("/")}`;
}
