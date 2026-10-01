"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Clock, Video, Globe, Check, CalendarCheck, Phone } from "lucide-react";
import { Card, Eyebrow } from "@/components/ui/Card";
import { Spinner, ErrorCard } from "@/components/ui/State";
import { RequirePerm } from "@/components/auth/Gate";
import { useLeads } from "@/components/providers/LeadsProvider";
import { useToast } from "@/components/providers/ToastProvider";
import { createBooking, getAvailability, listBookings } from "@/lib/api/bookings";
import { ApiError } from "@/lib/api/client";
import type { Availability, Booking } from "@/lib/types";
import { dayLabel, fmtTime, initials, isoDay } from "@/lib/format";
import { cn } from "@/lib/utils/cn";

interface Day { iso: string; dom: number; dow: string; label: string }

/** The next `n` days in India time. */
function nextDays(n: number): Day[] {
  const out: Day[] = [];
  const now = Date.now();
  for (let i = 0; i < n; i++) {
    const d = new Date(now + i * 86400000);
    const iso = isoDay(d);
    out.push({
      iso,
      dom: Number(iso.slice(8, 10)),
      dow: d.toLocaleDateString("en-IN", { weekday: "short", timeZone: "Asia/Kolkata" }),
      label: i === 0 ? "Today" : i === 1 ? "Tomorrow" : d.toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: "Asia/Kolkata" }),
    });
  }
  return out;
}

export default function AppointmentsPage() {
  return (
    <RequirePerm perm="bookings:create" message="Booking is available to admins, managers and counsellors.">
      <Suspense fallback={<Spinner />}>
        <Appointments />
      </Suspense>
    </RequirePerm>
  );
}

function Appointments() {
  const { leads, counsellors, loading } = useLeads();
  const toast = useToast();
  const params = useSearchParams();
  const preselectLead = params.get("lead") ?? "";

  const days = useMemo(() => nextDays(14), []);
  const [counsellorId, setCounsellorId] = useState("");
  const [leadId, setLeadId] = useState(preselectLead);
  const [day, setDay] = useState<Day>(days[0]);
  const [mode, setMode] = useState<"video" | "phone">("video");
  const [avail, setAvail] = useState<Availability | null>(null);
  const [availError, setAvailError] = useState<string | null>(null);
  const [slot, setSlot] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmed, setConfirmed] = useState<Booking | null>(null);
  const [upcoming, setUpcoming] = useState<Booking[] | null>(null);
  const [upcomingError, setUpcomingError] = useState<string | null>(null);

  const activeCounsellorId = counsellorId || counsellors[0]?.id || "";
  const activeLeadId = leadId || leads[0]?.id || "";
  const counsellor = counsellors.find((c) => c.id === activeCounsellorId);
  const lead = leads.find((l) => l.id === activeLeadId);

  const loadUpcoming = useCallback(() => {
    listBookings(0, 30)
      .then((rows) => { setUpcoming(rows); setUpcomingError(null); })
      .catch((err) => setUpcomingError(err instanceof ApiError ? err.message : "Could not load bookings."));
  }, []);

  useEffect(() => { loadUpcoming(); }, [loadUpcoming]);

  // Real availability whenever the counsellor or the day changes.
  useEffect(() => {
    if (!activeCounsellorId) return;
    setAvail(null);
    setAvailError(null);
    setSlot(null);
    getAvailability(activeCounsellorId, day.iso)
      .then(setAvail)
      .catch((err) => setAvailError(err instanceof ApiError ? err.message : "Could not load availability."));
  }, [activeCounsellorId, day.iso]);

  async function confirm() {
    if (!slot || !lead || !activeCounsellorId) return;
    setBusy(true);
    try {
      const b = await createBooking({ lead_id: lead.id, counsellor_id: activeCounsellorId, date: day.iso, time: slot, mode });
      setConfirmed(b);
      toast(`Booked ${lead.name} · ${day.label} ${slot}`);
      setSlot(null);
      getAvailability(activeCounsellorId, day.iso).then(setAvail).catch(() => {});
      loadUpcoming();
    } catch (err) {
      toast(err instanceof ApiError ? err.message : "Could not book that slot", "error");
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <Spinner />;

  return (
    <div className="space-y-5">
      <div>
        <Eyebrow>Book a session</Eyebrow>
        <h1 className="mt-1.5 text-[24px] font-extrabold tracking-[-0.02em]">Appointments</h1>
        <p className="mt-1 text-[12.5px] text-mut">Booked here exactly as Maya books on a call: same meeting link, same WhatsApp confirmation.</p>
      </div>

      {confirmed && (
        <Card className="flex flex-wrap items-center gap-4 border-emerald-400/30 bg-emerald-400/[0.06]">
          <span className="grid h-11 w-11 place-items-center rounded-full bg-emerald-400/15 text-emerald-300"><CalendarCheck className="h-5 w-5" /></span>
          <div className="flex-1">
            <p className="text-[14px] font-bold">Booked: {confirmed.lead_name}, {dayLabel(confirmed.scheduled_at)} at {fmtTime(confirmed.scheduled_at)}</p>
            <p className="text-[12px] text-soft">
              {confirmed.counsellor_name ? `With ${confirmed.counsellor_name} · ` : ""}
              {confirmed.meeting_url ? "Meeting link created" : confirmed.meeting_error ? `Meeting link failed: ${confirmed.meeting_error}` : "Phone session"}
              {" · "}WhatsApp {confirmed.whatsapp_status}{confirmed.whatsapp_error ? `: ${confirmed.whatsapp_error}` : ""}
            </p>
          </div>
          <Link href={`/leads/${confirmed.lead_id}`} className="rounded-full border border-line-2 bg-panel px-4 py-2 text-[13px] text-soft hover:text-ink">Open lead</Link>
          <button onClick={() => setConfirmed(null)} className="rounded-full border border-line-2 bg-panel px-4 py-2 text-[13px] text-soft hover:text-ink">Book another</button>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[320px_1fr]">
        <Card>
          <div className="flex items-center gap-3">
            <div className="grid h-12 w-12 shrink-0 place-items-center rounded-full font-bold text-[#0a0a0d] [background:conic-gradient(from_210deg,#f4f5fa,#8890a2,#b79cff,#f4f5fa)]">
              {counsellor ? initials(counsellor.name) : "?"}
            </div>
            <div className="flex-1">
              <select value={activeCounsellorId} onChange={(e) => setCounsellorId(e.target.value)} className="w-full rounded-lg border border-line-2 bg-bg-2 px-2 py-1.5 text-[13px] font-bold text-ink">
                {counsellors.length === 0 && <option value="">No counsellors yet</option>}
                {counsellors.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
              <p className="mt-1 text-[11px] text-mut">Counsellor</p>
            </div>
          </div>
          <div className="mt-4 border-t border-line pt-4">
            <p className="text-[13px] font-semibold">Counselling session</p>
            <div className="mt-2 space-y-2 text-[13px] text-soft">
              <p className="flex items-center gap-2"><Clock className="h-3.5 w-3.5" /> {avail?.slot_minutes ?? 30} minutes</p>
              <div className="flex items-center gap-2">
                {mode === "video" ? <Video className="h-3.5 w-3.5" /> : <Phone className="h-3.5 w-3.5" />}
                <select value={mode} onChange={(e) => setMode(e.target.value as "video" | "phone")} className="rounded-md border border-line bg-bg-2 px-2 py-0.5 text-[12px] text-ink">
                  <option value="video">Video call, link sent on WhatsApp</option>
                  <option value="phone">Phone call</option>
                </select>
              </div>
              <p className="flex items-center gap-2"><Globe className="h-3.5 w-3.5" /> {avail?.timezone ?? "Asia/Kolkata"} (IST)</p>
            </div>
          </div>
          <div className="mt-4 border-t border-line pt-4">
            <span className="mb-1.5 block text-[12px] text-soft">Booking for</span>
            <select value={activeLeadId} onChange={(e) => setLeadId(e.target.value)} className="w-full rounded-lg border border-line-2 bg-bg-2 px-3 py-2 text-[13px] text-ink">
              {leads.length === 0 && <option value="">No leads available</option>}
              {leads.map((l) => <option key={l.id} value={l.id}>{l.name} · {l.phone}</option>)}
            </select>
          </div>
        </Card>

        <Card>
          <h2 className="text-[16px] font-bold">Pick a date</h2>
          <div className="mt-3 flex gap-2 overflow-x-auto pb-1">
            {days.map((d) => (
              <button
                key={d.iso}
                onClick={() => setDay(d)}
                className={cn(
                  "flex min-w-[64px] flex-col items-center rounded-xl border px-2 py-2 transition-colors",
                  d.iso === day.iso ? "border-violet bg-violet/15 text-ink" : "border-line bg-panel text-soft hover:border-line-2",
                )}
              >
                <span className="font-mono text-[10px] uppercase text-mut">{d.dow}</span>
                <span className="text-[16px] font-bold">{d.dom}</span>
                <span className="text-[9px] text-mut">{d.label === "Today" || d.label === "Tomorrow" ? d.label : ""}</span>
              </button>
            ))}
          </div>

          <div className="mt-5 border-t border-line pt-4">
            <p className="mb-3 text-[13px] font-semibold">Available slots · {day.label}</p>
            {availError ? (
              <ErrorCard message={availError} />
            ) : avail === null ? (
              <Spinner className="h-24" />
            ) : avail.slots.length === 0 ? (
              <p className="py-6 text-center text-[13px] text-mut">No free slots on this day. Try another date.</p>
            ) : (
              <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-5">
                {avail.slots.map((s) => (
                  <button key={s} onClick={() => setSlot(s)} className={cn(
                    "h-11 rounded-lg border text-[13px] font-medium transition-colors",
                    s === slot ? "border-violet bg-violet text-white" : "border-line bg-panel text-soft hover:border-line-2",
                  )}>{s}</button>
                ))}
              </div>
            )}
            {avail && avail.taken.length > 0 && (
              <p className="mt-3 text-[11.5px] text-mut">Already booked: {avail.taken.join(", ")}</p>
            )}
          </div>

          <div className="mt-4 flex items-center justify-between border-t border-line pt-4">
            <p className="flex items-center gap-1.5 text-[12px] text-emerald-300"><Check className="h-3.5 w-3.5" /> Saved to the lead and sent on WhatsApp</p>
            <button onClick={confirm} disabled={!slot || !lead || busy} className={cn("rounded-full bg-ink px-4 py-2 text-[13px] font-semibold text-[#0a0a0d]", (!slot || !lead || busy) && "opacity-40")}>
              {busy ? "Booking" : slot ? `Confirm ${day.label}, ${slot}` : "Select a slot"}
            </button>
          </div>
        </Card>
      </div>

      <Card className="p-0">
        <div className="px-5 py-4">
          <h2 className="text-[16px] font-bold">Upcoming</h2>
          <p className="text-[12px] text-mut">Every booked session in the next 30 days, by Maya or by the team.</p>
        </div>
        {upcomingError && <div className="px-5 pb-5"><ErrorCard message={upcomingError} onRetry={loadUpcoming} /></div>}
        {upcoming === null && !upcomingError && <Spinner className="min-h-[100px]" />}
        {upcoming && (
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-y border-line text-left font-mono text-[10px] uppercase tracking-wide text-mut">
                  <th className="px-5 py-2.5 font-medium">When</th>
                  <th className="py-2.5 font-medium">Lead</th>
                  <th className="py-2.5 font-medium">Counsellor</th>
                  <th className="py-2.5 font-medium">Meeting</th>
                  <th className="py-2.5 font-medium">WhatsApp</th>
                  <th className="py-2.5 pr-5 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {upcoming.filter((b) => b.status === "booked").map((b) => (
                  <tr key={b.id} className="border-b border-white/5 hover:bg-panel">
                    <td className="px-5 py-3 whitespace-nowrap">{dayLabel(b.scheduled_at)}, {fmtTime(b.scheduled_at)}</td>
                    <td className="py-3"><Link href={`/leads/${b.lead_id}`} className="font-semibold hover:text-violet-2">{b.lead_name}</Link><div className="text-[11px] text-mut">{b.lead_phone}</div></td>
                    <td className="py-3 text-soft">{b.counsellor_name ?? "Not set"}</td>
                    <td className="py-3">
                      {b.meeting_url ? <a href={b.meeting_url} target="_blank" rel="noreferrer" className="text-violet-2 hover:underline">Open link</a> : <span className="text-mut">{b.meeting_error ? "Failed" : "Phone"}</span>}
                    </td>
                    <td className={cn("py-3", b.whatsapp_status === "sent" ? "text-emerald-300" : b.whatsapp_status === "failed" ? "text-red-300" : "text-mut")}>{b.whatsapp_status}</td>
                    <td className="py-3 pr-5 text-soft">{b.status}</td>
                  </tr>
                ))}
                {upcoming.filter((b) => b.status === "booked").length === 0 && (
                  <tr><td colSpan={6} className="py-8 text-center text-[13px] text-mut">Nothing booked in the next 30 days.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
