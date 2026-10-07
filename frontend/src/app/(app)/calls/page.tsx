"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Card, Eyebrow } from "@/components/ui/Card";
import { Spinner, ErrorCard, Empty } from "@/components/ui/State";
import { LiquidOrb } from "@/components/visuals/LiquidOrb";
import { getCall, listCalls } from "@/lib/api/calls";
import { ApiError } from "@/lib/api/client";
import { useCached } from "@/lib/hooks/useCached";
import type { Call, CallDetail } from "@/lib/types";
import { callStatusLabel } from "@/lib/labels";
import { fmtDuration, fmtTime, relative } from "@/lib/format";
import { cn } from "@/lib/utils/cn";

const FILTERS = [
  { id: "", label: "All" },
  { id: "completed", label: "Completed" },
  { id: "no-answer", label: "No answer" },
  { id: "failed", label: "Failed" },
  { id: "in-progress", label: "Live" },
];

export default function CallsPage() {
  const [filter, setFilter] = useState("");
  const [activeId, setActiveId] = useState("");
  const [detail, setDetail] = useState<CallDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);

  // One cache entry per filter; the last list paints at once, then refreshes.
  const fetchCalls = useCallback(async (): Promise<Call[]> => (await listCalls({ status: filter || undefined })).items, [filter]);
  const { data: calls, error, loading, reload: load } = useCached(`calls:${filter || "all"}`, fetchCalls, "Could not load calls.");

  const active = calls?.find((c) => c.id === activeId) ?? calls?.[0];

  // Fetch the transcript for the selected call; poll while it is live.
  useEffect(() => {
    if (!active) { setDetail(null); return; }
    let stop = false;
    const fetchDetail = () =>
      getCall(active.id)
        .then((d) => { if (!stop) { setDetail(d); setDetailError(null); } })
        .catch((err) => { if (!stop) setDetailError(err instanceof ApiError ? err.message : "Could not load the transcript."); });
    fetchDetail();
    const live = ["queued", "ringing", "in-progress"].includes(active.status);
    const t = live ? setInterval(fetchDetail, 5000) : null;
    return () => { stop = true; if (t) clearInterval(t); };
  }, [active]);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <Eyebrow>Voice AI · Maya</Eyebrow>
          <h1 className="mt-1.5 text-[24px] font-extrabold tracking-[-0.02em]">Calls</h1>
        </div>
        <div className="flex gap-1.5">
          {FILTERS.map((f) => (
            <button key={f.id} onClick={() => setFilter(f.id)} className={cn("rounded-full border px-3 py-1.5 text-[12px]", filter === f.id ? "border-line-2 bg-panel-2 text-ink" : "border-line bg-panel text-soft hover:text-ink")}>{f.label}</button>
          ))}
        </div>
      </div>

      {error && <ErrorCard message={error} onRetry={load} />}
      {loading && !error && <Spinner />}
      {calls?.length === 0 && <Empty>No calls yet. Submit the lead form and Maya will place the first one.</Empty>}

      {calls && calls.length > 0 && (
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-[300px_1fr]">
          <div className="max-h-[75vh] space-y-2 overflow-y-auto pr-1">
            {calls.map((c) => {
              const live = ["queued", "ringing", "in-progress"].includes(c.status);
              return (
                <button key={c.id} onClick={() => setActiveId(c.id)} className={cn(
                  "w-full rounded-xl border p-3 text-left transition-colors",
                  c.id === active?.id ? "border-line-2 bg-panel-2" : "border-line bg-panel hover:border-line-2",
                )}>
                  <div className="flex items-center justify-between gap-2">
                    <b className="truncate text-[13px]">{c.lead_name}</b>
                    <span className="shrink-0 font-mono text-[10px] text-mut">{relative(c.started_at ?? c.created_at)}</span>
                  </div>
                  <p className="mt-0.5 text-[11.5px] text-mut">
                    {live && <span className="mr-1.5 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />}
                    {callStatusLabel(c.status)}{c.duration_seconds ? ` · ${fmtDuration(c.duration_seconds)}` : ""}{c.score !== null ? ` · ${c.score}` : ""}
                  </p>
                </button>
              );
            })}
          </div>

          {active && (
            <div className="grid grid-cols-1 gap-5 xl:grid-cols-[1.4fr_1fr]">
              <Card className="flex flex-col">
                <div className="grid place-items-center py-2">
                  <LiquidOrb className="h-32 w-32" />
                  <p className="mt-2 text-[13px] font-semibold">Maya · AI counsellor</p>
                  <p className="text-[11px] text-mut">
                    Call with <Link href={`/leads/${active.lead_id}`} className="text-violet-2 hover:underline">{active.lead_name}</Link> · {active.lead_phone}
                  </p>
                </div>
                {detailError && <p className="mt-2 rounded-xl border border-red-500/30 bg-red-500/[0.06] px-3 py-2 text-[12px] text-red-300">{detailError}</p>}
                {active.error && <p className="mt-2 rounded-xl border border-red-500/30 bg-red-500/[0.06] px-3 py-2 text-[12px] text-red-300">{active.error}</p>}
                <div className="mt-2 max-h-[420px] space-y-2.5 overflow-y-auto rounded-2xl border border-line bg-panel p-4">
                  {detail?.transcript.map((t, i) => (
                    <div key={i} className={cn("max-w-[85%] rounded-xl px-3 py-2 text-[13px]", t.role === "assistant" ? "bg-violet/15 text-ink" : "ml-auto border border-line bg-bg-2 text-soft")}>
                      <p className="font-mono text-[9.5px] uppercase tracking-wide text-mut">{t.role === "assistant" ? "Maya" : "Lead"}{t.at ? ` · ${fmtTime(t.at)}` : ""}</p>
                      <p className="mt-0.5">{t.text}</p>
                    </div>
                  ))}
                  {detail && detail.transcript.length === 0 && <p className="py-4 text-center text-[12px] text-mut">No transcript recorded.</p>}
                  {!detail && !detailError && <Spinner className="min-h-[120px]" />}
                </div>
                <div className="mt-4 flex flex-wrap items-center gap-2 font-mono text-[11px] text-soft">
                  <span className="rounded-lg border border-line bg-panel px-2.5 py-1.5">Status · <b className="text-ink">{callStatusLabel(active.status)}</b></span>
                  <span className="rounded-lg border border-line bg-panel px-2.5 py-1.5">Intent · <b className="text-violet-2">{active.intent ?? "not set"}</b></span>
                  <span className="ml-auto rounded-lg border border-line bg-panel px-2.5 py-1.5">{fmtDuration(active.duration_seconds) || "0:00"} · {active.turns} exchanges</span>
                </div>
              </Card>

              <Card>
                <div className="flex items-center justify-between">
                  <h2 className="text-[15px] font-bold">What Maya learned</h2>
                  <span className="rounded-full bg-violet-2/15 px-2 py-0.5 text-[10px] font-semibold text-violet-2">from the conversation</span>
                </div>
                {active.summary ? (
                  <pre className="mt-3 whitespace-pre-wrap rounded-xl border border-line bg-bg-2 p-3 font-sans text-[12.5px] text-soft">{active.summary}</pre>
                ) : (
                  <p className="mt-3 text-[12px] text-mut">{["queued", "ringing", "in-progress"].includes(active.status) ? "Written when the call ends." : "No summary for this call."}</p>
                )}
                <dl className="mt-4 space-y-3">
                  {Object.entries(active.extraction ?? {}).map(([k, v]) => (
                    <div key={k}>
                      <dt className="font-mono text-[10px] uppercase tracking-wide text-mut">{k.replace(/_/g, " ")}</dt>
                      <dd className="text-[14px] font-medium text-violet-2">{String(v ?? "")}</dd>
                    </div>
                  ))}
                </dl>
                <div className="mt-5 border-t border-line pt-4">
                  <p className="font-mono text-[10px] uppercase tracking-wide text-mut">Lead score</p>
                  <p className="text-gradient text-[44px] font-extrabold leading-none">{active.score ?? "n/a"}</p>
                  <p className="text-[11px] text-mut">{active.score === null ? "Not scored" : "/ 100 · after this call"}</p>
                </div>
              </Card>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
