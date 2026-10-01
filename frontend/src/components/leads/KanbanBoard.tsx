"use client";

import { useState } from "react";
import Link from "next/link";
import { useLeads } from "@/components/providers/LeadsProvider";
import { STAGES, TEMP_DOT, sourceLabel, temperature, leadStatusLabel } from "@/lib/labels";
import type { Lead, Stage } from "@/lib/types";
import { cn } from "@/lib/utils/cn";
import { relative } from "@/lib/format";

export function KanbanBoard({ leads, editable, showLost }: { leads: Lead[]; editable: boolean; showLost: boolean }) {
  const { setStage } = useLeads();
  const [dragId, setDragId] = useState<string | null>(null);
  const [overStage, setOverStage] = useState<Stage | null>(null);
  const columns = showLost ? STAGES : STAGES.filter((s) => s.id !== "lost");

  function drop(stage: Stage) {
    if (dragId) {
      const lead = leads.find((l) => l.id === dragId);
      if (lead && lead.stage !== stage) setStage(dragId, stage);
    }
    setDragId(null);
    setOverStage(null);
  }

  return (
    <div className={cn("grid grid-cols-2 gap-3 md:grid-cols-3", showLost ? "xl:grid-cols-6" : "xl:grid-cols-5")}>
      {columns.map((s) => {
        const col = leads.filter((l) => l.stage === s.id);
        const isOver = overStage === s.id && dragId !== null;
        return (
          <div
            key={s.id}
            onDragOver={(e) => { if (editable && dragId) { e.preventDefault(); setOverStage(s.id); } }}
            onDragLeave={() => setOverStage((v) => (v === s.id ? null : v))}
            onDrop={(e) => { e.preventDefault(); drop(s.id); }}
            className={cn("rounded-2xl border p-2.5 transition-colors", isOver ? "border-violet-2/60 bg-violet/10" : "border-line bg-panel/50")}
          >
            <div className="mb-2 flex items-center justify-between px-1 text-[11px] font-semibold uppercase tracking-wide text-soft">
              <span>{s.label}</span>
              <span className="rounded-full bg-white/10 px-2 py-0.5 text-mut">{col.length}</span>
            </div>
            <div className="space-y-2">
              {col.map((l) => {
                const t = temperature(l.score);
                return (
                  <div
                    key={l.id}
                    draggable={editable}
                    onDragStart={() => setDragId(l.id)}
                    onDragEnd={() => { setDragId(null); setOverStage(null); }}
                    className={cn(
                      "rounded-xl border border-line bg-bg-2 p-3 transition-all",
                      editable && "cursor-grab active:cursor-grabbing hover:border-line-2",
                      dragId === l.id && "opacity-40",
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <Link href={`/leads/${l.id}`} className="truncate text-[13px] font-semibold hover:text-violet-2">{l.name}</Link>
                      <span className="flex shrink-0 items-center gap-1 text-[10px] text-mut">
                        <span className={`h-1.5 w-1.5 rounded-full ${TEMP_DOT[t]}`} /> {l.score ?? "n/a"}
                      </span>
                    </div>
                    <p className="mt-0.5 truncate text-[11px] text-mut">{l.product_or_course}</p>
                    <p className="mt-2 flex items-center justify-between font-mono text-[10px] text-soft">
                      <span className="truncate">{sourceLabel(l.source)}</span>
                      <span className="shrink-0 text-mut">{relative(l.created_at)}</span>
                    </p>
                    <p className="mt-1 text-[10.5px] text-mut">
                      {leadStatusLabel(l.status)}{l.assigned_name ? ` · ${l.assigned_name}` : ""}
                    </p>
                  </div>
                );
              })}
              {col.length === 0 && (
                <p className="px-1 py-4 text-center text-[11px] text-mut">{isOver ? "Drop here" : "No leads"}</p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
