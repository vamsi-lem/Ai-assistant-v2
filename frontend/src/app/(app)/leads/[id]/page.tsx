"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Phone, CalendarPlus, Video, ChevronDown, ChevronUp, ShieldCheck, ShieldOff, RefreshCw } from "lucide-react";
import { Card, Eyebrow } from "@/components/ui/Card";
import { Spinner, ErrorCard } from "@/components/ui/State";
import { ScoreChip } from "@/components/leads/ScoreChip";
import { useLeads } from "@/components/providers/LeadsProvider";
import { useRole } from "@/components/providers/RoleProvider";
import { useToast } from "@/components/providers/ToastProvider";
import { addNote, assignLead, callAgain, getLeadDetail, setStage } from "@/lib/api/leads";
import { resendWhatsApp, setBookingStatus } from "@/lib/api/bookings";
import { ApiError } from "@/lib/api/client";
import type { Booking, CallDetail, LeadDetail, LeadEvent, Stage } from "@/lib/types";
import { STAGES, callStatusLabel, languageLabel, leadStatusLabel, sourceLabel, stageLabel } from "@/lib/labels";
import { fmtDateTime, fmtDuration, fmtTime, initials, relative, dayLabel } from "@/lib/format";
import { cn } from "@/lib/utils/cn";

export default function LeadDetailPage({ params }: { params: { id: string } }) {
  const { can } = useRole();
  const { counsellors, refresh: refreshBoard } = useLeads();
  const toast = useToast();
  const [data, setData] = useState<LeadDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [calling, setCalling] = useState(false);
  const [note, setNote] = useState("");

  const load = useCallback(() => {
    setError(null);
    getLeadDetail(params.id)
      .then(setData)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load this lead."));
  }, [params.id]);

  useEffect(() => {
    load();
  }, [load]);

  // While a call is live, keep the page fresh so the transcript grows on screen.
  useEffect(() => {
    if (!data) return;
    const live = data.calls.some((c) => ["queued", "ringing", "in-progress"].includes(c.status));
    if (!live) return;
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [data, load]);

  if (error) return <ErrorCard message={error} onRetry={load} />;
  if (!data) return <Spinner />;

  const { lead, calls, bookings, notes, events } = data;
  const currentIdx = STAGES.findIndex((s) => s.id === lead.stage);

  async function doCall() {
    setCalling(true);
    try {
      const r = await callAgain(lead.id);
      if (r.call) toast(`Maya is calling ${lead.name}`);
      else toast(r.call_skipped_reason ?? "The call was not placed", "info");
      load();
      refreshBoard();
    } catch (err) {
      toast(err instanceof ApiError ? err.message : "Could not start the call", "error");
    } finally {
      setCalling(false);
    }
  }

  async function doAssign(id: string) {
    try {
      await assignLead(lead.id, id || null);
      toast(id ? "Assigned" : "Moved back to the incoming queue", "info");
      load();
      refreshBoard();
    } catch (err) {
      toast(err instanceof ApiError ? err.message : "Could not assign", "error");
    }
  }

  async function doStage(stage: Stage) {
    try {
      await setStage(lead.id, stage);
      toast(`Stage set to ${stageLabel(stage)}`, "info");
      load();
      refreshBoard();
    } catch (err) {
      toast(err instanceof ApiError ? err.message : "Could not change the stage", "error");
    }
  }

  async function submitNote(e: React.FormEvent) {
    e.preventDefault();
    const text = note.trim();
    if (!text) return;
    try {
      await addNote(lead.id, text);
      setNote("");
      toast("Note added");
      load();
    } catch (err) {
      toast(err instanceof ApiError ? err.message : "Could not save the note", "error");
    }
  }

  async function doResend(b: Booking) {
    try {
      await resendWhatsApp(b.id);
      toast("WhatsApp sent");
      load();
    } catch (err) {
      toast(err instanceof ApiError ? err.message : "Could not send", "error");
    }
  }

  async function doBookingStatus(b: Booking, status: Booking["status"]) {
    try {
      await setBookingStatus(b.id, status);
      toast(`Booking marked ${status.replace("_", " ")}`, "info");
      load();
    } catch (err) {
      toast(err instanceof ApiError ? err.message : "Could not update the booking", "error");
    }
  }

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <Link href="/leads" className="inline-flex items-center gap-2 text-[13px] text-soft hover:text-ink">
        <ArrowLeft className="h-4 w-4" /> Back to pipeline
      </Link>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[300px_1fr]">
        {/* Left column: who they are */}
        <div className="space-y-4">
          <Card className="text-center">
            <div className="mx-auto grid h-16 w-16 place-items-center rounded-full text-xl font-extrabold text-[#0a0a0d] [background:conic-gradient(from_210deg,#f4f5fa,#8890a2,#b79cff,#f4f5fa)]">
              {initials(lead.name)}
            </div>
            <p className="mt-3 text-[17px] font-bold">{lead.name}</p>
            <p className="text-[12px] text-mut">{languageLabel(lead.preferred_language)} · {sourceLabel(lead.source)}</p>
            <div className="mt-3"><ScoreChip score={lead.score} /></div>
          </Card>

          <Card>
            <p className="font-mono text-[10px] uppercase tracking-wide text-mut">Lead score</p>
            <p className="text-gradient text-[46px] font-extrabold leading-none">{lead.score ?? "n/a"}</p>
            <p className="text-[11px] text-mut">{lead.score === null ? "Set after Maya's first conversation" : "/ 100 · from the last conversation"}</p>
          </Card>

          <Card className="space-y-2.5 text-[13px]">
            <Row label="Phone" value={lead.phone} />
            <Row label="Email" value={lead.email ?? "none"} />
            <Row label="Course" value={lead.product_or_course} />
            <Row label="Call outcome" value={leadStatusLabel(lead.status)} />
            <Row label="Added" value={fmtDateTime(lead.created_at)} />
            {lead.callback_time && <Row label="Callback" value={lead.callback_time} />}
            <div className="flex items-center justify-between">
              <span className="text-mut">Consent</span>
              {lead.consent_given ? (
                <span className="flex items-center gap-1 text-emerald-300"><ShieldCheck className="h-3.5 w-3.5" /> {fmtDateTime(lead.consent_at) || "given"}</span>
              ) : (
                <span className="flex items-center gap-1 text-red-300"><ShieldOff className="h-3.5 w-3.5" /> not given</span>
              )}
            </div>
            {can("leads:assign") ? (
              <div>
                <span className="mb-1.5 block text-[11px] text-mut">Assigned to</span>
                <select value={lead.assigned_to ?? ""} onChange={(e) => doAssign(e.target.value)} className="w-full rounded-lg border border-line-2 bg-bg-2 px-3 py-2 text-[13px] text-ink">
                  <option value="">Unassigned</option>
                  {counsellors.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </div>
            ) : (
              <Row label="Assigned to" value={lead.assigned_name ?? "Unassigned"} />
            )}
            {can("leads:edit") && (
              <div>
                <span className="mb-1.5 block text-[11px] text-mut">Stage</span>
                <select value={lead.stage} onChange={(e) => doStage(e.target.value as Stage)} className="w-full rounded-lg border border-line-2 bg-bg-2 px-3 py-2 text-[13px] text-ink">
                  {STAGES.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
                </select>
              </div>
            )}
          </Card>

          {lead.notes && (
            <Card>
              <Eyebrow>Form notes and callbacks</Eyebrow>
              <pre className="mt-2 whitespace-pre-wrap font-sans text-[12.5px] text-soft">{lead.notes}</pre>
            </Card>
          )}

          <div className="grid grid-cols-2 gap-2">
            {can("calls:start") && (
              <button
                onClick={doCall}
                disabled={calling || !lead.consent_given || lead.status === "do_not_call"}
                title={!lead.consent_given ? "No consent recorded" : lead.status === "do_not_call" ? "Marked do not call" : "Maya rings them again"}
                className="flex flex-col items-center gap-1 rounded-xl border border-line bg-panel py-3 text-[11px] text-soft hover:border-line-2 hover:text-ink disabled:opacity-50"
              >
                <Phone className="h-4 w-4" /> {calling ? "Calling" : "Call again"}
              </button>
            )}
            {can("bookings:create") && (
              <Link href={`/appointments?lead=${lead.id}`} className="flex flex-col items-center gap-1 rounded-xl border border-line bg-panel py-3 text-[11px] text-soft hover:border-line-2 hover:text-ink">
                <CalendarPlus className="h-4 w-4" /> Book a slot
              </Link>
            )}
          </div>
        </div>

        {/* Right column: what happened */}
        <div className="space-y-4">
          <Card>
            <Eyebrow>Lead journey</Eyebrow>
            <div className="mt-4 flex items-center gap-1 overflow-x-auto">
              {STAGES.filter((s) => s.id !== "lost").map((s, i, arr) => (
                <div key={s.id} className="flex flex-1 items-center">
                  <div className={cn(
                    "flex-1 whitespace-nowrap rounded-lg border px-2 py-2 text-center text-[11px] font-semibold",
                    lead.stage === "lost" ? "border-line bg-panel text-mut" :
                    i < currentIdx ? "border-violet bg-violet text-white" :
                    i === currentIdx ? "border-violet-2 bg-violet-2/20 text-violet-2" :
                    "border-line bg-panel text-mut",
                  )}>{s.label}</div>
                  {i < arr.length - 1 && <div className={`h-0.5 w-3 shrink-0 ${i < currentIdx && lead.stage !== "lost" ? "bg-violet" : "bg-line"}`} />}
                </div>
              ))}
            </div>
            {lead.stage === "lost" && <p className="mt-2 text-[12px] text-mut">Marked lost. Change the stage on the left to reopen.</p>}
          </Card>

          <Card>
            <div className="flex items-center justify-between">
              <Eyebrow>Bookings</Eyebrow>
              <span className="text-[11px] text-mut">{bookings.length}</span>
            </div>
            <div className="mt-3 space-y-2">
              {bookings.length === 0 && <p className="py-3 text-[12.5px] text-mut">No slot booked yet.</p>}
              {bookings.map((b) => <BookingRow key={b.id} b={b} onResend={doResend} onStatus={doBookingStatus} canEdit={can("leads:edit")} />)}
            </div>
          </Card>

          <Card>
            <div className="flex items-center justify-between">
              <Eyebrow>Calls</Eyebrow>
              <span className="text-[11px] text-mut">{calls.length}</span>
            </div>
            <div className="mt-3 space-y-2">
              {calls.length === 0 && <p className="py-3 text-[12.5px] text-mut">Maya has not called yet.</p>}
              {calls.map((c) => <CallRow key={c.id} c={c} />)}
            </div>
          </Card>

          <Card>
            <Eyebrow>Activity</Eyebrow>
            <div className="mt-2">
              {events.map((e, i) => <EventRow key={e.id} e={e} last={i === events.length - 1} />)}
              {events.length === 0 && <p className="py-6 text-center text-[13px] text-mut">No activity yet.</p>}
            </div>
          </Card>

          <Card>
            <Eyebrow>Notes</Eyebrow>
            {can("leads:edit") && (
              <form onSubmit={submitNote} className="mt-3 flex gap-2">
                <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Add a note" className="flex-1 rounded-xl border border-line bg-bg-2 px-3.5 py-2.5 text-[13.5px] text-ink outline-none focus:border-line-2" />
                <button type="submit" disabled={!note.trim()} className="rounded-full bg-ink px-4 text-[13px] font-semibold text-[#0a0a0d] disabled:opacity-40">Save</button>
              </form>
            )}
            <div className="mt-3 space-y-2">
              {notes.map((n) => (
                <div key={n.id} className="rounded-xl border border-line bg-panel p-3 text-[13px]">
                  <p className="whitespace-pre-wrap">{n.body}</p>
                  <p className="mt-1 text-[11px] text-mut">{n.author_name ?? "System"} · {relative(n.created_at)}</p>
                </div>
              ))}
              {notes.length === 0 && <p className="py-2 text-[12px] text-mut">No notes yet.</p>}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <span className="shrink-0 text-mut">{label}</span>
      <span className="text-right font-medium">{value}</span>
    </div>
  );
}

const WA_CHIP: Record<Booking["whatsapp_status"], string> = {
  sent: "bg-emerald-400/15 text-emerald-300",
  pending: "bg-amber-300/15 text-amber-300",
  failed: "bg-red-500/15 text-red-300",
  skipped: "bg-white/10 text-mut",
};

function BookingRow({ b, onResend, onStatus, canEdit }: { b: Booking; onResend: (b: Booking) => void; onStatus: (b: Booking, s: Booking["status"]) => void; canEdit: boolean }) {
  return (
    <div className="rounded-xl border border-line bg-panel p-3.5 text-[13px]">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="font-semibold">{dayLabel(b.scheduled_at)}, {fmtTime(b.scheduled_at)} · {b.duration_minutes} min</p>
          <p className="text-[11.5px] text-mut">
            {b.counsellor_name ? `With ${b.counsellor_name}` : "No counsellor set"} · {b.meeting_provider ?? "phone"} · booked {relative(b.created_at)}
          </p>
        </div>
        <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-semibold", b.status === "booked" ? "bg-violet-2/15 text-violet-2" : "bg-white/10 text-mut")}>{b.status.replace("_", " ")}</span>
      </div>
      <div className="mt-2.5 flex flex-wrap items-center gap-2 text-[11.5px]">
        {b.meeting_url ? (
          <a href={b.meeting_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 rounded-lg border border-line px-2.5 py-1 text-soft hover:text-ink"><Video className="h-3 w-3" /> Meeting link</a>
        ) : (
          <span className="rounded-lg border border-line px-2.5 py-1 text-mut">{b.meeting_error ? `Link failed: ${b.meeting_error}` : "No meeting link"}</span>
        )}
        <span className={cn("rounded-lg px-2.5 py-1", WA_CHIP[b.whatsapp_status])}>WhatsApp {b.whatsapp_status}{b.whatsapp_error ? `: ${b.whatsapp_error}` : ""}</span>
        {canEdit && b.whatsapp_status !== "sent" && (
          <button onClick={() => onResend(b)} className="inline-flex items-center gap-1 rounded-lg border border-line px-2.5 py-1 text-soft hover:text-ink"><RefreshCw className="h-3 w-3" /> Resend</button>
        )}
        {canEdit && b.status === "booked" && (
          <span className="ml-auto flex gap-1">
            <button onClick={() => onStatus(b, "completed")} className="rounded-lg border border-line px-2.5 py-1 text-soft hover:text-ink">Completed</button>
            <button onClick={() => onStatus(b, "no_show")} className="rounded-lg border border-line px-2.5 py-1 text-soft hover:text-ink">No show</button>
            <button onClick={() => onStatus(b, "cancelled")} className="rounded-lg border border-line px-2.5 py-1 text-soft hover:text-ink">Cancel</button>
          </span>
        )}
      </div>
    </div>
  );
}

function CallRow({ c }: { c: CallDetail }) {
  const [open, setOpen] = useState(false);
  const live = ["queued", "ringing", "in-progress"].includes(c.status);
  return (
    <div className="rounded-xl border border-line bg-panel text-[13px]">
      <button onClick={() => setOpen((v) => !v)} className="flex w-full items-center justify-between gap-3 p-3.5 text-left">
        <div className="min-w-0">
          <p className="font-semibold">
            {callStatusLabel(c.status)}{live && <span className="ml-2 inline-block h-2 w-2 animate-pulse rounded-full bg-emerald-400" />}
          </p>
          <p className="text-[11.5px] text-mut">
            {fmtDateTime(c.started_at ?? c.created_at)}{c.duration_seconds ? ` · ${fmtDuration(c.duration_seconds)}` : ""} · {c.turns} exchanges
            {c.score !== null ? ` · score ${c.score}` : ""}{c.intent ? ` · ${c.intent}` : ""}
          </p>
          {c.error && <p className="mt-1 text-[11.5px] text-red-300">{c.error}</p>}
        </div>
        {open ? <ChevronUp className="h-4 w-4 shrink-0 text-mut" /> : <ChevronDown className="h-4 w-4 shrink-0 text-mut" />}
      </button>
      {open && (
        <div className="space-y-3 border-t border-line p-3.5">
          {c.summary && (
            <div className="rounded-lg border border-line bg-bg-2 p-3">
              <p className="font-mono text-[10px] uppercase text-mut">Summary from Maya</p>
              <pre className="mt-1 whitespace-pre-wrap font-sans text-[12.5px] text-soft">{c.summary}</pre>
            </div>
          )}
          {c.extraction && Object.keys(c.extraction).length > 0 && (
            <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {Object.entries(c.extraction).map(([k, v]) => (
                <div key={k} className="rounded-lg border border-line bg-bg-2 px-3 py-2">
                  <dt className="font-mono text-[10px] uppercase text-mut">{k.replace(/_/g, " ")}</dt>
                  <dd className="text-[12.5px] font-medium">{String(v ?? "")}</dd>
                </div>
              ))}
            </dl>
          )}
          <div className="max-h-[360px] space-y-2 overflow-y-auto">
            {c.transcript.map((t, i) => (
              <div key={i} className={cn("max-w-[85%] rounded-xl px-3 py-2 text-[12.5px]", t.role === "assistant" ? "bg-violet/15 text-ink" : "ml-auto border border-line bg-bg-2 text-soft")}>
                <p className="font-mono text-[9.5px] uppercase tracking-wide text-mut">{t.role === "assistant" ? "Maya" : "Lead"}{t.at ? ` · ${fmtTime(t.at)}` : ""}</p>
                <p className="mt-0.5">{t.text}</p>
              </div>
            ))}
            {c.transcript.length === 0 && <p className="py-3 text-center text-[12px] text-mut">No transcript recorded.</p>}
          </div>
        </div>
      )}
    </div>
  );
}

const EVENT_LABEL: Record<string, { label: string; dot: string }> = {
  lead_created: { label: "Lead captured", dot: "bg-blue-400" },
  call_started: { label: "Maya called", dot: "bg-emerald-400" },
  call_ended: { label: "Call ended", dot: "bg-emerald-400" },
  booking_created: { label: "Slot booked", dot: "bg-violet-2" },
  booking_updated: { label: "Booking updated", dot: "bg-violet-2" },
  whatsapp_sent: { label: "WhatsApp sent", dot: "bg-emerald-400" },
  whatsapp_failed: { label: "WhatsApp failed", dot: "bg-red-400" },
  stage_changed: { label: "Stage changed", dot: "bg-amber-300" },
  assigned: { label: "Assigned", dot: "bg-amber-300" },
  note_added: { label: "Note added", dot: "bg-warm" },
  callback_noted: { label: "Callback requested", dot: "bg-warm" },
};

function EventRow({ e, last }: { e: LeadEvent; last: boolean }) {
  const meta = EVENT_LABEL[e.kind] ?? { label: e.kind.replace(/_/g, " "), dot: "bg-violet-2" };
  const detail = typeof e.data?.detail === "string" ? e.data.detail : "";
  return (
    <div className="flex gap-4 border-b border-line/60 py-3.5 last:border-0">
      <div className="flex flex-col items-center">
        <span className={`mt-1 h-3 w-3 rounded-full ${meta.dot}`} />
        {!last && <span className="mt-1 w-px flex-1 bg-line" />}
      </div>
      <div className="min-w-0">
        <p className="text-[13.5px] font-semibold">{meta.label}</p>
        <p className="mt-0.5 text-[12px] text-mut">{detail ? `${detail} · ` : ""}{e.actor_name ? `${e.actor_name} · ` : ""}{fmtDateTime(e.created_at)}</p>
      </div>
    </div>
  );
}
