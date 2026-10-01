"use client";

import { useState } from "react";
import { UserPlus } from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import { useLeads } from "@/components/providers/LeadsProvider";
import { useRole } from "@/components/providers/RoleProvider";
import { useToast } from "@/components/providers/ToastProvider";
import { addLeadManually } from "@/lib/api/leads";
import { ApiError } from "@/lib/api/client";
import { COURSES, CONSENT_TEXT } from "@/components/leads/LeadForm";

const fld = "w-full rounded-xl border border-line bg-bg px-3 py-2.5 text-[13.5px] text-ink outline-none focus:border-line-2";

/**
 * A lead typed in by a counsellor (walk in, phone enquiry, a list from a
 * client). Saved with source "manual". Maya does not call automatically;
 * the counsellor presses "Call again" on the lead page when the lead has
 * agreed to it.
 */
export function AddLeadModal() {
  const { refresh, counsellors } = useLeads();
  const { can } = useRole();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const empty = { name: "", phone: "", email: "", course: COURSES[0], notes: "", consent: false, assigned_to: "" };
  const [f, setF] = useState(empty);
  const set = (k: keyof typeof f, v: string | boolean) => setF((s) => ({ ...s, [k]: v }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!f.name.trim() || f.phone.trim().length < 10) return;
    setBusy(true);
    setError(null);
    try {
      await addLeadManually({
        name: f.name.trim(),
        phone: f.phone.trim(),
        email: f.email.trim() || undefined,
        product_or_course: f.course,
        notes: f.notes.trim() || undefined,
        consent_given: f.consent,
        consent_text: f.consent ? `${CONSENT_TEXT} (recorded by counsellor)` : undefined,
        assigned_to: f.assigned_to || null,
      });
      await refresh();
      toast(`${f.name.trim()} added`);
      setOpen(false);
      setF(empty);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not add the lead");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button onClick={() => setOpen(true)} className="inline-flex items-center gap-2 rounded-full bg-violet px-4 py-2 text-[13px] font-semibold text-white">
        <UserPlus className="h-4 w-4" /> Add lead
      </button>

      <Modal open={open} onClose={() => setOpen(false)} title="Add a lead by hand">
        <form onSubmit={submit} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <Input label="Name" value={f.name} onChange={(v) => set("name", v)} />
            <Input label="Phone" value={f.phone} onChange={(v) => set("phone", v)} placeholder="98765 43210" />
            <Input label="Email (optional)" value={f.email} onChange={(v) => set("email", v)} />
            <label className="block">
              <span className="mb-1.5 block text-[12px] text-soft">Course</span>
              <select className={fld} value={f.course} onChange={(e) => set("course", e.target.value)}>
                {COURSES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </label>
          </div>
          {can("leads:assign") && (
            <label className="block">
              <span className="mb-1.5 block text-[12px] text-soft">Assign to</span>
              <select className={fld} value={f.assigned_to} onChange={(e) => set("assigned_to", e.target.value)}>
                <option value="">Leave in the incoming queue</option>
                {counsellors.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </label>
          )}
          <label className="block">
            <span className="mb-1.5 block text-[12px] text-soft">Notes (optional)</span>
            <textarea className={`${fld} min-h-[72px] resize-y`} value={f.notes} onChange={(e) => set("notes", e.target.value)} />
          </label>
          <label className="flex items-start gap-3 rounded-xl border border-line bg-bg p-3 text-[12.5px] text-soft">
            <input type="checkbox" checked={f.consent} onChange={(e) => set("consent", e.target.checked)} className="mt-0.5 h-4 w-4 accent-[var(--violet)]" />
            <span>The lead has agreed to an automated AI voice call. Without this Maya will refuse to dial them.</span>
          </label>
          {error && <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-[12.5px] text-red-300">{error}</p>}
          <div className="flex justify-end gap-2 pt-1">
            <button type="button" onClick={() => setOpen(false)} className="rounded-full border border-line px-4 py-2 text-[13px] text-soft hover:text-ink">Cancel</button>
            <button type="submit" disabled={busy || !f.name.trim() || f.phone.trim().length < 10} className="rounded-full bg-violet px-4 py-2 text-[13px] font-semibold text-white disabled:opacity-40">
              {busy ? "Saving" : "Add lead"}
            </button>
          </div>
        </form>
      </Modal>
    </>
  );
}

function Input({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[12px] text-soft">{label}</span>
      <input className={fld} value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}
