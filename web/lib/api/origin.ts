import "server-only";

/** Where server components reach the API (the browser uses the same-origin `/v1` rewrite). */
export const API_ORIGIN = process.env.API_ORIGIN ?? "http://localhost:8000";
