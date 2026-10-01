/**
 * Calls and transcripts.
 *
 * Backend: backend/app/routers/calls.py
 */

import { request, qs } from "@/lib/api/client";
import type { Call, CallDetail, CallStatusResponse, Page } from "@/lib/types";

export interface CallFilters {
  lead_id?: string;
  status?: string;
  limit?: number;
  offset?: number;
}

export function listCalls(filters: CallFilters = {}): Promise<Page<Call>> {
  return request<Page<Call>>(`/calls${qs({ limit: 200, ...filters })}`);
}

/** One call with its full transcript. */
export function getCall(id: string): Promise<CallDetail> {
  return request<CallDetail>(`/calls/${id}`);
}

/** Public. The form page polls this while the carrier rings the lead. */
export function getCallStatus(id: string): Promise<CallStatusResponse> {
  return request<CallStatusResponse>(`/calls/${id}/status`, { auth: false });
}
