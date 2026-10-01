/**
 * Leads: the public form, the board, the queue, the detail page.
 *
 * Backend: backend/app/routers/leads.py
 */

import { request, qs } from "@/lib/api/client";
import type { Lead, LeadCreateResponse, LeadDetail, LeadInput, LeadNote, Page, Stage } from "@/lib/types";

/** Public form. No token. The backend saves the lead, then Maya calls. */
export function createLead(input: LeadInput): Promise<LeadCreateResponse> {
  return request<LeadCreateResponse>("/leads", { method: "POST", body: input, auth: false });
}

export interface LeadFilters {
  stage?: Stage | "";
  assigned_to?: string; // profile id, or "unassigned"
  search?: string;
  source?: string;
  limit?: number;
  offset?: number;
}

/** Leads the signed in user may see. Counsellors get only their own. */
export function listLeads(filters: LeadFilters = {}): Promise<Page<Lead>> {
  return request<Page<Lead>>(`/leads${qs({ limit: 500, ...filters })}`);
}

/** Lead plus every call, transcript, booking, note and event. */
export function getLeadDetail(id: string): Promise<LeadDetail> {
  return request<LeadDetail>(`/leads/${id}/detail`);
}

export function setStage(id: string, stage: Stage): Promise<Lead> {
  return request<Lead>(`/leads/${id}`, { method: "PATCH", body: { stage } });
}

/** Assign or unassign (null). One call per lead keeps the event log honest. */
export function assignLead(id: string, counsellorId: string | null): Promise<Lead> {
  return request<Lead>(`/leads/${id}`, { method: "PATCH", body: { assigned_to: counsellorId } });
}

export function addNote(id: string, body: string): Promise<LeadNote> {
  return request<LeadNote>(`/leads/${id}/notes`, { method: "POST", body: { body } });
}

/** Ring an existing lead again. Same consent gate and cooldown as the form. */
export function callAgain(id: string): Promise<LeadCreateResponse> {
  return request<LeadCreateResponse>(`/leads/${id}/call`, { method: "POST" });
}

/** Add a lead by hand from the dashboard. Saved with source "manual"; no automatic call. */
export function addLeadManually(input: LeadInput & { assigned_to?: string | null }): Promise<Lead> {
  return request<Lead>("/leads/manual", { method: "POST", body: input });
}
