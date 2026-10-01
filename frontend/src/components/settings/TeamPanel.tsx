"use client";

import { useCallback, useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Modal } from "@/components/ui/Modal";
import { Spinner, ErrorCard } from "@/components/ui/State";
import { useRole } from "@/components/providers/RoleProvider";
import { useToast } from "@/components/providers/ToastProvider";
import { inviteMember, listTeam, removeMember, updateMember } from "@/lib/api/team";
import { ApiError } from "@/lib/api/client";
import { ROLES, roleLabel } from "@/lib/rbac";
import type { Profile, Role } from "@/lib/types";
import { cn } from "@/lib/utils/cn";

const btnV = "inline-flex items-center gap-1.5 rounded-full bg-violet px-4 py-2 text-[13px] font-semibold text-white";
const btnG = "inline-flex items-center gap-1.5 rounded-full border border-line-2 bg-panel px-4 py-2 text-[13px] font-semibold text-soft hover:text-ink";
const fld = "w-full rounded-lg border border-line bg-bg-2 px-3 py-2.5 text-[13.5px] text-ink outline-none focus:border-line-2";
const chip = "rounded-md border border-line bg-panel px-2 py-0.5 font-mono text-[10px] text-soft";

/** Members, their roles, and invitations. Admins edit; managers see. */
export function TeamPanel() {
  const { can, userId } = useRole();
  const toast = useToast();
  const canManage = can("team:manage");
  const [team, setTeam] = useState<Profile[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [inviting, setInviting] = useState(false);
  const [f, setF] = useState<{ name: string; email: string; role: Role }>({ name: "", email: "", role: "counsellor" });
  const [busy, setBusy] = useState(false);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [removing, setRemoving] = useState<Profile | null>(null);
  const [removeError, setRemoveError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    listTeam().then(setTeam).catch((err) => setError(err instanceof ApiError ? err.message : "Could not load the team."));
  }, []);

  useEffect(() => { load(); }, [load]);

  async function invite(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setInviteError(null);
    try {
      await inviteMember({ name: f.name.trim(), email: f.email.trim(), role: f.role });
      toast(`Invitation sent to ${f.email.trim()}`);
      setInviting(false);
      setF({ name: "", email: "", role: "counsellor" });
      load();
    } catch (err) {
      setInviteError(err instanceof ApiError ? err.message : "Could not send the invitation");
    } finally {
      setBusy(false);
    }
  }

  async function setRole(p: Profile, role: Role) {
    try {
      await updateMember(p.id, { role });
      toast(`${p.name} is now ${roleLabel(role)}`, "info");
      load();
    } catch (err) {
      toast(err instanceof ApiError ? err.message : "Could not change the role", "error");
    }
  }

  async function confirmRemove() {
    if (!removing) return;
    setBusy(true);
    setRemoveError(null);
    try {
      await removeMember(removing.id);
      toast(`${removing.name} removed`, "info");
      setRemoving(null);
      load();
    } catch (err) {
      setRemoveError(err instanceof ApiError ? err.message : "Could not remove this member");
    } finally {
      setBusy(false);
    }
  }

  async function setActive(p: Profile, active: boolean) {
    try {
      await updateMember(p.id, { active });
      toast(active ? `${p.name} reactivated` : `${p.name} deactivated`, "info");
      load();
    } catch (err) {
      toast(err instanceof ApiError ? err.message : "Could not update", "error");
    }
  }

  return (
    <Card>
      <div className="flex items-center justify-between">
        <h3 className="text-[15px] font-bold">Team and roles</h3>
        {canManage && <button onClick={() => setInviting(true)} className={btnV}><Plus className="h-4 w-4" /> Invite</button>}
      </div>
      <p className="mt-1 text-[13px] text-soft">
        Roles decide what each person sees. Counsellors see only leads assigned to them; managers and admins see everything; admins manage this list.
      </p>

      {error && <div className="mt-3"><ErrorCard message={error} onRetry={load} /></div>}
      {!team && !error && <Spinner className="min-h-[120px]" />}

      {team && (
        <table className="mt-3 w-full text-[13px]">
          <thead><tr className="border-b border-line text-left font-mono text-[10px] uppercase tracking-wide text-mut"><th className="py-2">Member</th><th>Role</th><th className="text-right">Status</th>{canManage && <th className="w-10"></th>}</tr></thead>
          <tbody>
            {team.map((m) => (
              <tr key={m.id} className={cn("border-b border-white/5", !m.active && "opacity-50")}>
                <td className="py-3"><b>{m.name}</b>{m.id === userId && <span className="ml-2 text-[10px] text-mut">you</span>}<div className="text-[11px] text-mut">{m.email}</div></td>
                <td>
                  {canManage && m.id !== userId ? (
                    <select value={m.role} onChange={(e) => setRole(m, e.target.value as Role)} className="rounded-lg border border-line-2 bg-bg-2 px-2 py-1 text-[12.5px] text-ink">
                      {ROLES.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
                    </select>
                  ) : (
                    <span className={chip}>{roleLabel(m.role)}</span>
                  )}
                </td>
                <td className="text-right">
                  {canManage && m.id !== userId ? (
                    <button onClick={() => setActive(m, !m.active)} className={cn("rounded-full px-2.5 py-0.5 text-[10px] font-semibold", m.active ? "bg-emerald-400/15 text-emerald-300" : "bg-white/10 text-mut")}>
                      {m.active ? "Active" : "Deactivated"}
                    </button>
                  ) : (
                    <span className={cn("rounded-full px-2.5 py-0.5 text-[10px] font-semibold", m.active ? "bg-emerald-400/15 text-emerald-300" : "bg-white/10 text-mut")}>{m.active ? "Active" : "Deactivated"}</span>
                  )}
                </td>
                {canManage && (
                  <td className="text-right">
                    {m.id !== userId && (
                      <button onClick={() => { setRemoving(m); setRemoveError(null); }} title="Remove this login" aria-label={`Remove ${m.name}`} className="grid h-7 w-7 place-items-center rounded-lg text-mut hover:bg-red-500/10 hover:text-red-300">
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </td>
                )}
              </tr>
            ))}
            {team.length === 0 && <tr><td colSpan={4} className="py-4 text-center text-[12px] text-mut">No members yet.</td></tr>}
          </tbody>
        </table>
      )}

      <Modal open={!!removing} onClose={() => setRemoving(null)} title="Remove this login?">
        {removing && (
          <div className="space-y-3 text-[13px]">
            <p><b>{removing.name}</b> ({removing.email}) will no longer be able to sign in. Leads assigned to them go back to the incoming queue; notes and timeline entries they wrote stay but lose their name.</p>
            <p className="text-soft">If this person has simply left the team, prefer <b>Deactivated</b>: it blocks sign in and keeps their name on everything they did.</p>
            {removeError && <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-[12.5px] text-red-300">{removeError}</p>}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setRemoving(null)} className={btnG}>Cancel</button>
              <button type="button" onClick={confirmRemove} disabled={busy} className={cn("inline-flex items-center gap-1.5 rounded-full bg-red-500/90 px-4 py-2 text-[13px] font-semibold text-white hover:bg-red-500", busy && "opacity-50")}>
                <Trash2 className="h-4 w-4" /> {busy ? "Removing" : "Remove"}
              </button>
            </div>
          </div>
        )}
      </Modal>

      <Modal open={inviting} onClose={() => setInviting(false)} title="Invite a team member">
        <form onSubmit={invite} className="space-y-3">
          <label className="block"><span className="mb-1.5 block text-[12px] text-soft">Name</span><input className={fld} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required /></label>
          <label className="block"><span className="mb-1.5 block text-[12px] text-soft">Email</span><input type="email" className={fld} value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} required /></label>
          <label className="block"><span className="mb-1.5 block text-[12px] text-soft">Role</span>
            <select className={fld} value={f.role} onChange={(e) => setF({ ...f, role: e.target.value as Role })}>
              {ROLES.map((r) => <option key={r.id} value={r.id}>{r.label}: {r.desc}</option>)}
            </select>
          </label>
          <p className="text-[12px] text-mut">They receive an email with a link to choose their password. The link is valid for 24 hours.</p>
          {inviteError && <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-[12.5px] text-red-300">{inviteError}</p>}
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setInviting(false)} className={btnG}>Cancel</button>
            <button type="submit" disabled={busy} className={cn(btnV, busy && "opacity-50")}>{busy ? "Sending" : "Send invitation"}</button>
          </div>
        </form>
      </Modal>
    </Card>
  );
}
