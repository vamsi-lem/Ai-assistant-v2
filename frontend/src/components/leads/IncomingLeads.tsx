"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Card } from "@/components/ui/Card";
import { Spinner, ErrorCard } from "@/components/ui/State";
import { ScoreChip } from "@/components/leads/ScoreChip";
import { useLeads } from "@/components/providers/LeadsProvider";
import { languageLabel, leadStatusLabel, sourceLabel } from "@/lib/labels";
import { relative } from "@/lib/format";
import { cn } from "@/lib/utils/cn";

const sel = "rounded-lg border border-line-2 bg-bg-2 px-3 py-1.5 text-[12.5px] text-ink";

/** Leads nobody owns yet. Pick some, choose a counsellor, assign. */
export function IncomingLeads() {
  const { leads, counsellors, loading, error, assign, refresh } = useLeads();
  const [source, setSource] = useState("all");
  const [lang, setLang] = useState("any");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [assignee, setAssignee] = useState("");
  const [busy, setBusy] = useState(false);

  const incoming = useMemo(() => leads.filter((l) => !l.assigned_to && l.stage !== "lost" && l.stage !== "converted"), [leads]);
  const activeAssignee = assignee || counsellors[0]?.id || "";

  const languages = useMemo(() => Array.from(new Set(incoming.map((l) => l.preferred_language ?? ""))).filter(Boolean), [incoming]);
  const sources = useMemo(() => Array.from(new Set(incoming.map((l) => l.source))), [incoming]);

  const rows = incoming.filter(
    (l) => (source === "all" || l.source === source) && (lang === "any" || l.preferred_language === lang),
  );
  const allChecked = rows.length > 0 && rows.every((r) => selected.has(r.id));

  function toggle(id: string) {
    setSelected((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  }
  const toggleAll = () => setSelected(allChecked ? new Set() : new Set(rows.map((r) => r.id)));

  async function doAssign() {
    if (selected.size === 0 || !activeAssignee) return;
    setBusy(true);
    await assign([...selected], activeAssignee);
    setSelected(new Set());
    setBusy(false);
  }

  if (error) return <ErrorCard message={error} onRetry={refresh} />;
  if (loading) return <Spinner />;

  return (
    <Card className="p-0">
      <div className="flex flex-wrap items-end justify-between gap-3 p-5">
        <div>
          <h2 className="text-[16px] font-bold">Unassigned · {incoming.length}</h2>
          <p className="mt-1 text-[13px] text-soft">Every lead Maya has spoken to (or tried to) that no counsellor owns yet.</p>
        </div>
        <div className="flex gap-2">
          <select className={sel} value={source} onChange={(e) => { setSource(e.target.value); setSelected(new Set()); }}>
            <option value="all">Source · All</option>
            {sources.map((s) => <option key={s} value={s}>{sourceLabel(s)}</option>)}
          </select>
          <select className={sel} value={lang} onChange={(e) => setLang(e.target.value)}>
            <option value="any">Language · Any</option>
            {languages.map((l) => <option key={l} value={l}>{languageLabel(l)}</option>)}
          </select>
        </div>
      </div>

      <div className="mx-5 mb-3 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line-2 bg-bg-2 px-3.5 py-2.5">
        <label className="flex items-center gap-2.5 text-[13px]">
          <input type="checkbox" checked={allChecked} onChange={toggleAll} className="h-4 w-4 accent-[var(--violet)]" />
          <b>{selected.size}</b> selected
        </label>
        <div className="flex flex-wrap items-center gap-2">
          <select className={sel} value={activeAssignee} onChange={(e) => setAssignee(e.target.value)}>
            {counsellors.length === 0 && <option value="">No counsellors yet</option>}
            {counsellors.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <button onClick={doAssign} disabled={busy || selected.size === 0 || !activeAssignee} className={cn("rounded-full bg-violet px-4 py-2 text-[13px] font-semibold text-white", (busy || selected.size === 0 || !activeAssignee) && "opacity-40")}>
            {busy ? "Assigning" : "Assign"}
          </button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-[13px]">
          <thead>
            <tr className="border-y border-line text-left font-mono text-[10px] uppercase tracking-wide text-mut">
              <th className="w-10 px-5 py-2.5"></th>
              <th className="py-2.5 font-medium">Lead</th>
              <th className="py-2.5 font-medium">Course</th>
              <th className="py-2.5 font-medium">Source</th>
              <th className="py-2.5 font-medium">Call outcome</th>
              <th className="py-2.5 font-medium">Score</th>
              <th className="py-2.5 font-medium">Language</th>
              <th className="py-2.5 pr-5 font-medium">Arrived</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((l) => (
              <tr key={l.id} className={cn("border-b border-white/5 hover:bg-panel", selected.has(l.id) && "bg-violet/[0.06]")}>
                <td className="px-5 py-3">
                  <input type="checkbox" checked={selected.has(l.id)} onChange={() => toggle(l.id)} className="h-4 w-4 accent-[var(--violet)]" />
                </td>
                <td className="py-3"><Link href={`/leads/${l.id}`} className="font-semibold hover:text-violet-2">{l.name}</Link><div className="text-[11px] text-mut">{l.phone}</div></td>
                <td className="py-3 text-soft">{l.product_or_course}</td>
                <td className="py-3"><span className="rounded-md border border-line bg-panel px-2 py-0.5 font-mono text-[10px] text-soft">{sourceLabel(l.source)}</span></td>
                <td className="py-3 text-soft">{leadStatusLabel(l.status)}</td>
                <td className="py-3"><ScoreChip score={l.score} /></td>
                <td className="py-3 text-soft">{languageLabel(l.preferred_language)}</td>
                <td className="py-3 pr-5 text-mut">{relative(l.created_at)}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan={8} className="py-10 text-center text-[13px] text-mut">All caught up. No unassigned leads for this filter.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
