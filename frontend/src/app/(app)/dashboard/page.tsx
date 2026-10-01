"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Phone, CalendarPlus, Video } from "lucide-react";
import { Card, Eyebrow } from "@/components/ui/Card";
import { Spinner, ErrorCard } from "@/components/ui/State";
import { ScoreChip } from "@/components/leads/ScoreChip";
import { useRole } from "@/components/providers/RoleProvider";
import { getDashboard } from "@/lib/api/dashboard";
import { ApiError } from "@/lib/api/client";
import type { DashboardSummary, Lead } from "@/lib/types";
import { leadStatusLabel, languageLabel, sourceLabel, TEMP_DOT, temperature } from "@/lib/labels";
import { fmtTime, relative } from "@/lib/format";

export default function DashboardPage() {
  const { user } = useRole();
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    getDashboard()
      .then(setData)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load the dashboard."));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-[26px] font-extrabold tracking-[-0.02em]">
          {greeting}, {user.name.split(" ")[0]}
        </h1>
        <p className="mt-1 text-[14px] text-soft">
          {data?.scope === "mine" ? "Showing the leads assigned to you." : "Showing activity across the whole account."}
        </p>
      </div>

      {error && <ErrorCard message={error} onRetry={load} />}
      {!data && !error && <Spinner />}

      {data && (
        <>
          <div className="grid grid-cols-2 gap-3.5 lg:grid-cols-5">
            <Kpi label={data.scope === "mine" ? "My leads" : "Total leads"} value={data.counts.leads} />
            <Kpi label="Calls today" value={data.counts.calls_today} />
            <Kpi label="Qualified" value={data.counts.qualified} />
            <Kpi label="Appointments today" value={data.counts.appointments_today} />
            <Kpi label="Converted" value={data.counts.converted} />
          </div>

          <Card className="p-0">
            <div className="flex items-center justify-between px-5 py-4">
              <div>
                <h2 className="text-[16px] font-bold">Priority queue</h2>
                <p className="text-[12px] text-mut">Open leads, highest score first. The score comes from what the lead said to Maya.</p>
              </div>
              <Link href="/leads" className="rounded-full border border-line-2 bg-panel px-3.5 py-1.5 text-[13px] text-soft hover:text-ink">
                Open the board
              </Link>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead>
                  <tr className="border-y border-line text-left font-mono text-[10px] uppercase tracking-wide text-mut">
                    <th className="px-5 py-2.5 font-medium">Lead</th>
                    <th className="px-3 py-2.5 font-medium">Course</th>
                    <th className="px-3 py-2.5 font-medium">Score</th>
                    <th className="px-3 py-2.5 font-medium">Last call</th>
                    <th className="px-3 py-2.5 font-medium">Source</th>
                    <th className="px-5 py-2.5 text-right font-medium">Open</th>
                  </tr>
                </thead>
                <tbody>
                  {data.queue.map((l) => <QueueRow key={l.id} lead={l} />)}
                  {data.queue.length === 0 && (
                    <tr><td colSpan={6} className="py-10 text-center text-[13px] text-mut">No open leads yet. Submit the form to see the first one arrive.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </Card>

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
            <Card>
              <Eyebrow>Today</Eyebrow>
              <h2 className="mt-2 text-[16px] font-bold">Appointments</h2>
              <div className="mt-3 space-y-2">
                {data.today.length === 0 && <p className="py-4 text-center text-[13px] text-mut">No appointments today.</p>}
                {data.today.map((b) => (
                  <div key={b.id} className="flex items-center justify-between gap-3 rounded-xl border border-line bg-panel px-3.5 py-3">
                    <div className="min-w-0">
                      <Link href={`/leads/${b.lead_id}`} className="text-[13px] font-medium hover:text-violet-2">{b.lead_name}</Link>
                      <p className="text-[11px] text-mut">
                        {b.meeting_url ? "Video" : "Phone"}{b.counsellor_name ? ` · with ${b.counsellor_name}` : ""}
                        {b.whatsapp_status === "failed" && <span className="text-red-300"> · WhatsApp failed</span>}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      {b.meeting_url && (
                        <a href={b.meeting_url} target="_blank" rel="noreferrer" title="Open the meeting" className="grid h-8 w-8 place-items-center rounded-lg border border-line text-soft hover:text-ink">
                          <Video className="h-3.5 w-3.5" />
                        </a>
                      )}
                      <span className="font-mono text-[12px] text-soft">{fmtTime(b.scheduled_at)}</span>
                    </div>
                  </div>
                ))}
              </div>
            </Card>

            <Card>
              <Eyebrow>Suggested next actions</Eyebrow>
              <h2 className="mt-2 text-[16px] font-bold">Follow ups</h2>
              <div className="mt-3 space-y-1">
                {suggestions(data.queue).map((t) => (
                  <Link key={t.id} href={`/leads/${t.id}`} className="flex items-center gap-3 rounded-xl px-2 py-2.5 hover:bg-panel">
                    <span className={`h-2 w-2 shrink-0 rounded-full ${t.dot}`} />
                    <span className="flex-1 text-[13px] text-soft">{t.label}</span>
                    <span className="rounded-full bg-white/10 px-2 py-0.5 text-[10px] font-semibold text-mut">{t.why}</span>
                  </Link>
                ))}
                {data.queue.length === 0 && <p className="py-6 text-center text-[13px] text-mut">Nothing waiting on you.</p>}
              </div>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}

function Kpi({ label, value }: { label: string; value: number }) {
  return (
    <Card className="hover:border-line-2">
      <p className="font-mono text-[10.5px] uppercase tracking-wider text-mut">{label}</p>
      <p className="mt-2 text-[32px] font-extrabold tracking-[-0.03em]">{value}</p>
    </Card>
  );
}

function QueueRow({ lead }: { lead: Lead }) {
  const t = temperature(lead.score);
  return (
    <tr className="border-b border-line/60 last:border-0 hover:bg-panel">
      <td className="px-5 py-3">
        <Link href={`/leads/${lead.id}`} className="font-semibold hover:text-violet-2">{lead.name}</Link>
        <p className="text-[11px] text-mut">{lead.phone} · {languageLabel(lead.preferred_language)}</p>
      </td>
      <td className="px-3 py-3 whitespace-nowrap text-soft">{lead.product_or_course}</td>
      <td className="px-3 py-3">
        <div className="flex items-center gap-2">
          <div className="h-1.5 w-16 overflow-hidden rounded-full bg-white/10">
            <div className={`h-full rounded-full ${TEMP_DOT[t]}`} style={{ width: `${lead.score ?? 0}%` }} />
          </div>
          <ScoreChip score={lead.score} />
        </div>
      </td>
      <td className="px-3 py-3 whitespace-nowrap text-[12px] text-soft">
        {leadStatusLabel(lead.status)}{lead.last_call_at ? ` · ${relative(lead.last_call_at)}` : ""}
      </td>
      <td className="px-3 py-3 whitespace-nowrap text-[12px] text-mut">{sourceLabel(lead.source)}</td>
      <td className="px-5 py-3">
        <div className="flex justify-end gap-1.5">
          <ActionBtn href={`/leads/${lead.id}`} icon={<Phone className="h-3 w-3" />} label="Detail" />
          <ActionBtn href={`/appointments?lead=${lead.id}`} icon={<CalendarPlus className="h-3 w-3" />} label="Book" />
        </div>
      </td>
    </tr>
  );
}

/**
 * Plain rules, not a model: what a counsellor would do next given the call
 * outcome and the stage. Shown as hints, never acted on automatically.
 */
function suggestions(queue: Lead[]) {
  return queue.slice(0, 5).map((l) => {
    if (l.status === "no_answer" || l.status === "failed") {
      return { id: l.id, label: `Try ${l.name} again, Maya could not reach them`, why: "No answer", dot: "bg-amber-300" };
    }
    if (l.stage === "appointment" && !l.next_booking_at) {
      return { id: l.id, label: `Confirm a slot with ${l.name}`, why: "No booking", dot: "bg-warm" };
    }
    if (l.stage === "qualified") {
      return { id: l.id, label: `Follow up with ${l.name} about ${l.product_or_course}`, why: "Qualified", dot: "bg-violet-2" };
    }
    if (l.callback_time) {
      return { id: l.id, label: `${l.name} asked for a callback: ${l.callback_time}`, why: "Callback", dot: "bg-warm" };
    }
    return { id: l.id, label: `Review Maya's notes on ${l.name}`, why: "New", dot: "bg-blue-400" };
  });
}

function ActionBtn({ href, icon, label }: { href: string; icon: React.ReactNode; label: string }) {
  return (
    <Link href={href} className="inline-flex items-center gap-1 rounded-lg border border-line-2 bg-panel px-2.5 py-1.5 text-[11px] text-soft hover:bg-panel-2 hover:text-ink">
      {icon}
      {label}
    </Link>
  );
}

