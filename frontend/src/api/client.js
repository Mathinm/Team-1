// Single entry point for every backend call.
//
// Live mode  : real FastAPI backend at /api (vite proxy in dev, nginx in Docker).
// Mock mode  : in-browser fake backend that follows the same contract (SAD 4.3),
//              so the UI can be built and demoed before the backend endpoints exist.
//              Turn on with VITE_USE_MOCK=true (see frontend/.env.development).

import { mockRequest } from "./mock/handlers.js";

export const USE_MOCK = import.meta.env?.VITE_USE_MOCK === "true";

const TOKEN_KEY = "pms.token";

export class ApiError extends Error {
  constructor(status, code, message, details) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: session lasts until reload */
  }
}

// Called on any 401 so the app can drop the session and go to the login page.
let onUnauthorized = () => {};
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn;
}

// Turn any backend error body into an ApiError.
// Supports the SAD 4.4 format {error: {code, message, details}} and
// FastAPI's default {detail: "..."} / {detail: [validation errors]}.
export function toApiError(status, body) {
  if (body?.error) {
    return new ApiError(status, body.error.code, body.error.message, body.error.details);
  }
  if (typeof body?.detail === "string") {
    return new ApiError(status, String(status), body.detail);
  }
  if (Array.isArray(body?.detail)) {
    const msg = body.detail.map((d) => d.msg).join("; ");
    return new ApiError(status, "VALIDATION", msg || "Invalid input", body.detail);
  }
  return new ApiError(status, String(status), defaultMessage(status));
}

function defaultMessage(status) {
  if (status === 401) return "Your session has ended. Please log in again.";
  if (status === 403) return "You don't have permission to do that.";
  if (status === 404) return "Not found.";
  if (status >= 500) return "Server error. Please try again.";
  return "Request failed.";
}

/**
 * request("GET", "/products")
 * request("POST", "/sales", { sku, quantity })
 * request("POST", "/sales/csv", formData)   // FormData is sent as multipart
 */
export async function request(method, path, body) {
  const token = getToken();

  if (USE_MOCK) {
    const res = await mockRequest(method, path, body, token);
    if (res.status >= 400) {
      const err = toApiError(res.status, res.body);
      if (res.status === 401 && path !== "/auth/login") onUnauthorized();
      throw err;
    }
    return res.body;
  }

  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  let payload;
  if (body instanceof FormData) {
    payload = body;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }

  let res;
  try {
    res = await fetch(`/api${path}`, { method, headers, body: payload });
  } catch {
    throw new ApiError(0, "NETWORK", "Can't reach the server. Check your connection.");
  }

  if (res.status === 204) return null;
  const isJson = res.headers.get("content-type")?.includes("application/json");
  const data = isJson ? await res.json().catch(() => null) : await res.blob();

  if (!res.ok) {
    if (res.status === 401 && path !== "/auth/login") onUnauthorized();
    throw toApiError(res.status, isJson ? data : null);
  }
  return data;
}
