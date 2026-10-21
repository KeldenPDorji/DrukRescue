// Tiny API client. Every call goes through the gateway at /api.
const TOKEN_KEY = "drukrescue.token";
const USER_KEY = "drukrescue.user";

export function session() {
  const token = sessionStorage.getItem(TOKEN_KEY);
  const user = JSON.parse(sessionStorage.getItem(USER_KEY) || "null");
  return token && user ? { token, user } : null;
}

export function saveSession({ access_token, user }) {
  sessionStorage.setItem(TOKEN_KEY, access_token);
  sessionStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearSession() {
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(USER_KEY);
}

export class ApiError extends Error {
  constructor(status, detail) {
    super(typeof detail === "string" ? detail : JSON.stringify(detail));
    this.status = status;
  }
}

export async function api(path, { method = "GET", body } = {}) {
  const headers = { Accept: "application/json" };
  const s = session();
  if (s) headers.Authorization = `Bearer ${s.token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const res = await fetch(`/api${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  if (res.status === 401 && s) {
    clearSession();
    location.reload();
  }
  const data = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, data?.detail ?? res.statusText);
  return data;
}

// Always build HTML from user content with this (or use textContent) to avoid XSS.
export function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

// Run fn now and every `ms` while the page is visible. Returns a stop function.
export function poll(fn, ms = 5000) {
  fn();
  const id = setInterval(() => document.visibilityState === "visible" && fn(), ms);
  return () => clearInterval(id);
}
