/**
 * Who is signed in, and the team.
 *
 * Backend: backend/app/routers/team.py
 */

import { request } from "@/lib/api/client";
import type { Profile, Role } from "@/lib/types";

/** The signed in user's profile, as the backend sees it. */
export function getMe(): Promise<Profile> {
  return request<Profile>("/me");
}

export function listTeam(): Promise<Profile[]> {
  return request<Profile[]>("/team");
}

/** People a lead can be assigned to or booked with. */
export async function listCounsellors(): Promise<Profile[]> {
  const team = await listTeam();
  return team.filter((p) => p.active && (p.role === "counsellor" || p.role === "manager" || p.role === "admin"));
}

/** Admin only. Supabase emails an invitation; the person sets their password from it. */
export function inviteMember(input: { email: string; name: string; role: Role }): Promise<Profile> {
  return request<Profile>("/team/invite", { method: "POST", body: input });
}

export function updateMember(id: string, patch: { role?: Role; active?: boolean; name?: string }): Promise<Profile> {
  return request<Profile>(`/team/${id}`, { method: "PATCH", body: patch });
}

/**
 * Admin only. Removes the login entirely. Their leads return to the incoming
 * queue; notes and timeline entries they wrote lose the author name. For
 * someone who has left the team, deactivating keeps the history intact.
 */
export function removeMember(id: string): Promise<void> {
  return request<void>(`/team/${id}`, { method: "DELETE" });
}
