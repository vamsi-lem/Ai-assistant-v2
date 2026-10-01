"use client";

import { useCallback, useEffect, useState } from "react";
import { Card } from "@/components/ui/Card";
import { Spinner, ErrorCard } from "@/components/ui/State";
import { getVoiceSettings } from "@/lib/api/settings";
import { ApiError } from "@/lib/api/client";
import type { VoiceSettings } from "@/lib/types";

/**
 * How Maya is configured right now, read from the agent's environment
 * through the backend. Read only: these values live in agent/.env and
 * the LiveKit agent secrets today. Editing arrives with the tenants table.
 */
export function VoicePanel() {
  const [v, setV] = useState<VoiceSettings | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    getVoiceSettings().then(setV).catch((err) => setError(err instanceof ApiError ? err.message : "Could not load settings."));
  }, []);

  useEffect(() => { load(); }, [load]);

  const rows: { label: string; value: string }[] = v
    ? [
        { label: "Assistant name", value: v.agent_name },
        { label: "Calls on behalf of", value: v.company },
        { label: "Conversation flow", value: v.flow },
        { label: "Languages offered", value: v.languages.join(", ") },
        { label: "Greeting language", value: v.greeting_language },
        { label: "Voice", value: `${v.tts_speaker} (${v.tts_model})` },
        { label: "Brain", value: `${v.llm_provider} · ${v.llm_model}` },
        { label: "Call transport", value: v.call_transport },
        { label: "Counsellor hours", value: v.counsellor_hours },
        { label: "Booking timezone", value: v.booking_timezone },
        { label: "Meeting links", value: v.meeting_provider },
        { label: "WhatsApp template", value: v.whatsapp_template },
      ]
    : [];

  return (
    <Card>
      <h3 className="text-[15px] font-bold">Voice AI agent</h3>
      <p className="mt-1 text-[13px] text-soft">
        What Maya uses on every call. To change a value, edit the agent environment and redeploy (docs/DEPLOY.md). Editing from here comes with multi tenant support.
      </p>
      {v && !v.agent_reported_at && (
        <p className="mt-2 rounded-lg border border-amber-300/30 bg-amber-300/[0.06] px-3 py-2 text-[12px] text-amber-300">
          The agent has not reported its settings yet. It does so on its first call after a deploy; the backend side (bookings, meetings, WhatsApp) is shown below.
        </p>
      )}
      {error && <div className="mt-3"><ErrorCard message={error} onRetry={load} /></div>}
      {!v && !error && <Spinner className="min-h-[120px]" />}
      {v && (
        <dl className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2">
          {rows.map((r) => (
            <div key={r.label} className="rounded-xl border border-line bg-bg-2 px-3.5 py-3">
              <dt className="font-mono text-[10px] uppercase tracking-wide text-mut">{r.label}</dt>
              <dd className="mt-0.5 text-[13.5px] font-medium">{r.value || "not set"}</dd>
            </div>
          ))}
        </dl>
      )}
    </Card>
  );
}
