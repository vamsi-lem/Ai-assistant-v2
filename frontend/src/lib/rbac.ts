/**
 * Roles and what each may do in the UI.
 *
 * This only decides what to show. The backend checks the same role on every
 * request, so hiding a button here is a courtesy, not the security.
 */

import type { Role } from "@/lib/types";

export const ROLES: { id: Role; label: string; desc: string }[] = [
  { id: "admin", label: "Admin", desc: "Everything, including the team" },
  { id: "manager", label: "Manager", desc: "All leads, assignment, bookings" },
  { id: "counsellor", label: "Counsellor", desc: "Only leads assigned to them" },
  { id: "viewer", label: "Viewer", desc: "Read only across all leads" },
];

export type Permission =
  | "console:view"   // the settings area
  | "team:manage"    // invite, change roles
  | "leads:viewAll"  // see every lead, not only assigned ones
  | "leads:assign"   // assign and the incoming queue
  | "leads:edit"     // stage, notes, add lead
  | "calls:start"    // call again
  | "bookings:create";

const MATRIX: Record<Permission, Role[]> = {
  "console:view": ["admin", "manager"],
  "team:manage": ["admin"],
  "leads:viewAll": ["admin", "manager", "viewer"],
  "leads:assign": ["admin", "manager"],
  "leads:edit": ["admin", "manager", "counsellor"],
  "calls:start": ["admin", "manager", "counsellor"],
  "bookings:create": ["admin", "manager", "counsellor"],
};

export function can(role: Role, perm: Permission): boolean {
  return MATRIX[perm].includes(role);
}

export function roleLabel(role: Role | string): string {
  return ROLES.find((r) => r.id === role)?.label ?? role;
}
