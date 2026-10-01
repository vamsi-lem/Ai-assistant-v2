"use client";

import { useRole } from "@/components/providers/RoleProvider";
import { roleLabel } from "@/lib/rbac";
import { initials } from "@/lib/format";

/** Read only chip showing the signed in user's role. The backend enforces the scope. */
export function RoleBadge() {
  const { role, user } = useRole();
  return (
    <div className="flex items-center gap-2 rounded-full border border-line bg-panel py-1 pl-1 pr-3 text-[12px] font-semibold text-soft">
      <span className="grid h-7 w-7 place-items-center rounded-full text-[10px] font-bold text-[#0a0a0d] [background:conic-gradient(from_210deg,#f4f5fa,#8890a2,#b79cff,#f4f5fa)]">
        {initials(user.name)}
      </span>
      <span className="hidden font-mono text-[10px] text-violet-2 sm:inline">{roleLabel(role).toUpperCase()}</span>
      <span className="hidden text-ink sm:inline">{user.name}</span>
    </div>
  );
}
