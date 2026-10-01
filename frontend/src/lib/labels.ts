/**
 * Human labels for the enum values the backend stores.
 */

import type { CallStatus, LeadStatus, Stage } from "@/lib/types";

export const STAGES: { id: Stage; label: string }[] = [
  { id: "new", label: "New" },
  { id: "contacted", label: "Contacted" },
  { id: "qualified", label: "Qualified" },
  { id: "appointment", label: "Appointment" },
  { id: "converted", label: "Converted" },
  { id: "lost", label: "Lost" },
];

/** The board shows the working stages; Lost has its own column at the end. */
export const BOARD_STAGES = STAGES;

export function stageLabel(stage: Stage | string): string {
  return STAGES.find((s) => s.id === stage)?.label ?? stage;
}

export const SOURCE_LABEL: Record<string, string> = {
  form: "Website form",
  whatsapp: "WhatsApp",
  meta_lead_ads: "Meta lead ads",
  google_forms: "Google Forms",
  manual: "Added by hand",
};

export function sourceLabel(source: string): string {
  return SOURCE_LABEL[source] ?? source;
}

export const LEAD_STATUS_LABEL: Record<LeadStatus, string> = {
  new: "Not called yet",
  calling: "Call in progress",
  contacted: "Spoke to Maya",
  no_answer: "No answer",
  failed: "Call failed",
  do_not_call: "Do not call",
};

export function leadStatusLabel(status: LeadStatus | string): string {
  return LEAD_STATUS_LABEL[status as LeadStatus] ?? status;
}

export const CALL_STATUS_LABEL: Record<CallStatus, string> = {
  queued: "Queued",
  ringing: "Ringing",
  "in-progress": "In progress",
  completed: "Completed",
  failed: "Failed",
  "no-answer": "No answer",
  busy: "Busy",
};

export function callStatusLabel(status: CallStatus | string): string {
  return CALL_STATUS_LABEL[status as CallStatus] ?? status;
}

export const LANGUAGE_LABEL: Record<string, string> = {
  "hi-IN": "Hindi",
  "en-IN": "English",
  "te-IN": "Telugu",
  "ta-IN": "Tamil",
  "kn-IN": "Kannada",
  "ml-IN": "Malayalam",
  "mr-IN": "Marathi",
  "bn-IN": "Bengali",
  "gu-IN": "Gujarati",
  "pa-IN": "Punjabi",
  "od-IN": "Odia",
};

export function languageLabel(code: string | null | undefined): string {
  if (!code) return "Not known yet";
  return LANGUAGE_LABEL[code] ?? code;
}

export type Temp = "Hot" | "Warm" | "Cold" | "Unscored";

/** Buckets for the score Maya gives after a call. */
export function temperature(score: number | null | undefined): Temp {
  if (score === null || score === undefined) return "Unscored";
  if (score >= 70) return "Hot";
  if (score >= 40) return "Warm";
  return "Cold";
}

export const TEMP_CHIP: Record<Temp, string> = {
  Hot: "text-warm border-warm/30 bg-warm/10",
  Warm: "text-amber-300 border-amber-300/25 bg-amber-300/10",
  Cold: "text-violet-2 border-violet-2/25 bg-violet-2/10",
  Unscored: "text-mut border-line bg-panel",
};

export const TEMP_DOT: Record<Temp, string> = {
  Hot: "bg-warm",
  Warm: "bg-amber-300",
  Cold: "bg-violet-2",
  Unscored: "bg-mut",
};
