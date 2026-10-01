"use client";

import { useEffect, useState } from "react";
import { PhoneCall, Check, AlertTriangle } from "lucide-react";
import { Brand } from "@/components/layout/Brand";
import { LeadForm } from "@/components/leads/LeadForm";
import { ApiError } from "@/lib/api/client";
import { createLead } from "@/lib/api/leads";
import { getCallStatus } from "@/lib/api/calls";
import { getHealth } from "@/lib/api/dashboard";
import type { Call, CallStatusResponse, Health, LeadInput } from "@/lib/types";
import { callStatusLabel } from "@/lib/labels";

const TERMINAL = new Set(["completed", "failed", "no-answer", "busy"]);

/**
 * The public enquiry form. The entry point to the whole pipeline.
 * No login: this page is what a lead sees from an ad or the website.
 */
export default function FormPage() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [skipped, setSkipped] = useState<string | null>(null);
  const [call, setCall] = useState<Call | null>(null);
  const [health, setHealth] = useState<Health | null>(null);

  // Read the backend's own account of itself once at load. Cheaper than
  // discovering a misconfiguration halfway through a submission.
  useEffect(() => {
    getHealth().then(setHealth).catch(() => setHealth(null));
  }, []);

  async function submit(input: LeadInput) {
    setBusy(true);
    setError(null);
    setSkipped(null);
    try {
      const result = await createLead(input);
      setSkipped(result.call_skipped_reason);
      if (result.call) setCall(result.call);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setCall(null);
    setError(null);
    setSkipped(null);
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-[640px] flex-col px-4 py-8 sm:py-12">
      <Brand href="/form" className="mb-8" />

      <header>
        <p className="font-mono text-[11.5px] uppercase tracking-[0.16em] text-violet-2">Talk to Maya</p>
        <h1 className="mt-2 text-[30px] font-extrabold tracking-[-0.03em]">Tell us what you are looking for</h1>
        <p className="mt-2 text-[14px] text-soft">
          Submit your enquiry and our AI assistant Maya will call you straight away to understand
          what you need and arrange a session with a counsellor.
        </p>
      </header>

      <div className="mt-6 space-y-4">
        {error && (
          <Notice tone="bad" title="Could not submit">
            <pre className="whitespace-pre-wrap font-mono text-[12px]">{error}</pre>
          </Notice>
        )}

        {skipped && !call && (
          <Notice tone="warn" title="Saved, but not called">
            <p>{skipped}</p>
            <button onClick={reset} className="mt-3 rounded-full border border-line-2 bg-panel px-4 py-2 text-[13px] text-soft hover:text-ink">Back to the form</button>
          </Notice>
        )}

        {skipped && call && (
          <Notice tone="bad" title="Your details are saved, but the call did not go through">
            <p>{skipped}</p>
          </Notice>
        )}

        {call ? <PhoneCallStatus call={call} onReset={reset} /> : !skipped && <LeadForm onSubmit={submit} busy={busy} />}
      </div>

      <footer className="mt-auto pt-10 font-mono text-[11px] text-mut">
        {health ? (
          <span>backend {health.status} · db {health.database}{health.transport ? ` · ${health.transport}` : ""}</span>
        ) : (
          <span>backend unreachable</span>
        )}
      </footer>
    </main>
  );
}

function Notice({ tone, title, children }: { tone: "bad" | "warn"; title: string; children: React.ReactNode }) {
  const ring = tone === "bad" ? "border-red-500/30 bg-red-500/[0.06]" : "border-amber-300/30 bg-amber-300/[0.06]";
  return (
    <div className={`rounded-2xl border p-4 text-[13.5px] ${ring}`}>
      <p className="flex items-center gap-2 font-semibold"><AlertTriangle className="h-4 w-4" /> {title}</p>
      <div className="mt-1.5 text-soft">{children}</div>
    </div>
  );
}

/**
 * Reports what the carrier is doing while the lead waits for the phone to
 * ring. Polls the public status endpoint every three seconds until the call
 * reaches a final state.
 */
function PhoneCallStatus({ call, onReset }: { call: Call; onReset: () => void }) {
  const [status, setStatus] = useState<CallStatusResponse | null>(null);
  const [ended, setEnded] = useState(false);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    let stop = false;
    async function poll() {
      try {
        const next = await getCallStatus(call.id);
        if (stop) return;
        setStatus(next);
        if (TERMINAL.has(next.call.status)) setEnded(true);
      } catch {
        // Keep polling; a blip should not end the page.
      }
    }
    poll();
    const timer = setInterval(poll, 3000);
    return () => { stop = true; clearInterval(timer); };
  }, [call.id]);

  useEffect(() => {
    if (ended) return;
    const t = setInterval(() => setElapsed((v) => v + 1), 1000);
    return () => clearInterval(t);
  }, [ended]);

  const current = status?.call.status ?? call.status;

  return (
    <div className="rounded-2xl border border-line bg-panel p-5">
      <div className="flex items-center gap-3">
        <span className={`grid h-11 w-11 place-items-center rounded-full ${ended ? "bg-emerald-400/15 text-emerald-300" : "bg-violet/15 text-violet-2"}`}>
          {ended ? <Check className="h-5 w-5" /> : <PhoneCall className="h-5 w-5 animate-pulse" />}
        </span>
        <div>
          <p className="text-[15px] font-bold">{ended ? "Call finished" : "Maya is calling your phone"}</p>
          <p className="text-[12px] text-mut">Phone call via carrier · {callStatusLabel(current)}{!ended && ` · ${elapsed}s`}</p>
        </div>
      </div>

      {status?.call.error && (
        <p className="mt-4 rounded-xl border border-red-500/30 bg-red-500/[0.06] px-3.5 py-3 text-[13px] text-red-300">{status.call.error}</p>
      )}

      <dl className="mt-4 grid grid-cols-2 gap-3 text-[13px]">
        <div className="rounded-xl border border-line bg-bg-2 px-3.5 py-3">
          <dt className="font-mono text-[10px] uppercase text-mut">Status</dt>
          <dd className="mt-0.5 font-semibold">{callStatusLabel(current)}</dd>
        </div>
        <div className="rounded-xl border border-line bg-bg-2 px-3.5 py-3">
          <dt className="font-mono text-[10px] uppercase text-mut">Exchanges</dt>
          <dd className="mt-0.5 font-semibold">{status?.turns ?? 0}</dd>
        </div>
      </dl>

      {status?.summary && (
        <div className="mt-4 rounded-xl border border-line bg-bg-2 px-3.5 py-3 text-[13px]">
          <p className="font-mono text-[10px] uppercase text-mut">What Maya noted</p>
          <pre className="mt-1 whitespace-pre-wrap font-sans text-soft">{status.summary}</pre>
        </div>
      )}

      {ended && (
        <button onClick={onReset} className="mt-4 rounded-full border border-line-2 bg-panel px-4 py-2 text-[13px] text-soft hover:text-ink">
          Submit another enquiry
        </button>
      )}
    </div>
  );
}
