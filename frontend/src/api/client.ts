/**
 * Backend calls.
 *
 * One place, so a change of host or an error-shape change is one edit.
 */

import type {
  Booking,
  BookingRow,
  CallStatusResponse,
  LeadCreateResponse,
  LeadInput,
} from '../types';

const BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api'
).replace(/\/+$/, '');

/** An error carrying whatever the server actually said, not a generic message. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json();

    // FastAPI puts validation failures in `detail` as an array of objects.
    if (Array.isArray(body?.detail)) {
      return body.detail
        .map((item: { loc?: string[]; msg?: string }) => {
          const field = item.loc?.filter((part) => part !== 'body').join('.');
          return field ? `${field}: ${item.msg}` : item.msg;
        })
        .filter(Boolean)
        .join('\n');
    }

    if (typeof body?.detail === 'string') return body.detail;
    return JSON.stringify(body);
  } catch {
    return `${response.status} ${response.statusText}`;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    });
  } catch {
    // A network-level failure here is almost always one of two things, and
    // saying which saves a lot of guessing.
    throw new ApiError(
      `Could not reach the backend at ${BASE_URL}. Either it is not running, ` +
        `or its CORS_ORIGINS does not include this page's address.`,
      0,
    );
  }

  if (!response.ok) {
    throw new ApiError(await readError(response), response.status);
  }

  return (await response.json()) as T;
}

export function createLead(input: LeadInput): Promise<LeadCreateResponse> {
  return request<LeadCreateResponse>('/leads', {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export function getCallStatus(callId: string): Promise<CallStatusResponse> {
  return request<CallStatusResponse>(`/calls/${callId}/status`);
}

export function getHealth(): Promise<Record<string, string>> {
  return request<Record<string, string>>('/health');
}

// --- Counsellor dashboard -----------------------------------------------
//
// Every call carries the dashboard key the counsellor typed in. It never
// lives in the build; it lives in their browser session.

function dashboardHeaders(key: string): HeadersInit {
  return { 'X-Dashboard-Key': key };
}

export function listBookings(key: string, daysBack = 1, daysAhead = 30): Promise<BookingRow[]> {
  return request<BookingRow[]>(`/bookings?days_back=${daysBack}&days_ahead=${daysAhead}`, {
    headers: dashboardHeaders(key),
  });
}

export function resendWhatsApp(key: string, bookingId: string): Promise<Booking> {
  return request<Booking>(`/bookings/${bookingId}/resend`, {
    method: 'POST',
    headers: dashboardHeaders(key),
  });
}

export function setBookingStatus(
  key: string,
  bookingId: string,
  status: Booking['status'],
): Promise<Booking> {
  return request<Booking>(`/bookings/${bookingId}/status`, {
    method: 'POST',
    headers: dashboardHeaders(key),
    body: JSON.stringify({ status }),
  });
}
