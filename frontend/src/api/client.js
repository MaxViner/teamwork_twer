export async function request(path, options = {}) {
  const response = await fetch(`/api${path}`, options);
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(typeof body?.detail === "string" ? body.detail : JSON.stringify(body?.detail || `HTTP ${response.status}`));
  }
  return response.json();
}
