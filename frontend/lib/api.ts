// Centralized API access: base URLs, optional API key, and auth headers.
// The API key is sent as the X-API-Key header (and as ?api_key= for WebSockets)
// only when NEXT_PUBLIC_API_KEY is set. When the backend has
// API_AUTH_ENABLED=false (the default), the header is simply omitted and
// requests work unauthenticated.
export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
export const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";
export const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "";

export const authHeaders = (): Record<string, string> =>
  API_KEY ? { "X-API-Key": API_KEY } : {};

export const wsUrl = (path: string): string =>
  API_KEY ? `${path}${path.includes("?") ? "&" : "?"}api_key=${API_KEY}` : path;
