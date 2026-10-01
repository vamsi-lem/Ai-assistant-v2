/**
 * The only place the backend URL appears.
 *
 * Every screen calls the backend through `request`. It attaches the signed
 * in user's token, turns FastAPI error bodies into readable messages, and
 * sends the user back to /login when the token is rejected.
 */

import { getAccessToken, signOutToLogin } from "@/lib/api/session";

const BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api").replace(/\/+$/, "");

/** An error carrying what the server actually said, not a generic message. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json();

    // FastAPI puts validation failures in `detail` as an array of objects.
    if (Array.isArray(body?.detail)) {
      return body.detail
        .map((item: { loc?: string[]; msg?: string }) => {
          const field = item.loc?.filter((part) => part !== "body").join(".");
          return field ? `${field}: ${item.msg}` : item.msg;
        })
        .filter(Boolean)
        .join("\n");
    }
    if (typeof body?.detail === "string") return body.detail;
    return JSON.stringify(body);
  } catch {
    return `${response.status} ${response.statusText}`;
  }
}

interface Options {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  /** Public endpoints (the lead form, health) send no token. */
  auth?: boolean;
}

export async function request<T>(path: string, opts: Options = {}): Promise<T> {
  const { method = "GET", body, auth = true } = opts;
  const headers: Record<string, string> = { "Content-Type": "application/json" };

  if (auth) {
    const token = await getAccessToken();
    if (!token) {
      throw new ApiError("You are signed out. Sign in again.", 401);
    }
    headers.Authorization = `Bearer ${token}`;
  }

  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
    });
  } catch {
    // A network level failure is almost always one of two things, and saying
    // which saves a lot of guessing.
    throw new ApiError(
      `Could not reach the backend at ${BASE_URL}. Either it is not running, ` +
        `or its CORS_ORIGINS does not include this page's address.`,
      0,
    );
  }

  if (response.status === 401 && auth) {
    // The backend refused the token. Say why on the login page rather than
    // bouncing silently, which looks like "sign in does nothing".
    const reason = await readError(response);
    await signOutToLogin(reason);
    throw new ApiError(reason, 401);
  }

  if (!response.ok) {
    throw new ApiError(await readError(response), response.status);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** Build a query string, skipping empty values. */
export function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const parts: string[] = [];
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`);
  }
  return parts.length ? `?${parts.join("&")}` : "";
}

export function apiBaseUrl(): string {
  return BASE_URL;
}
