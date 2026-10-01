/**
 * Shapes shared with the backend.
 *
 * Field names are the database column names, exactly as the backend returns
 * them (backend/app/schemas.py). If one side changes, change the other.
 */

// ---------------------------------------------------------------------------
// People
// ---------------------------------------------------------------------------

/** Stored lowercase in profiles.role. */
export type Role = "admin" | "manager" | "counsellor" | "viewer";

export interface Profile {
  id: string;
  name: string;
  email: string;
  role: Role;
  active: boolean;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Leads
// ---------------------------------------------------------------------------

/** Pipeline stage: a counsellor decision, moved by hand on the board. */
export type Stage = "new" | "contacted" | "qualified" | "appointment" | "converted" | "lost";

/** Call outcome, written by the backend and the agent. Not the same thing as the stage. */
export type LeadStatus = "new" | "calling" | "contacted" | "no_answer" | "failed" | "do_not_call";

export type Source = "form" | "whatsapp" | "meta_lead_ads" | "google_forms" | "manual";

export interface Lead {
  id: string;
  name: string;
  phone: string;
  email: string | null;
  product_or_course: string;
  notes: string | null;
  preferred_language: string | null;
  callback_time: string | null;
  callback_notes: string | null;
  source: Source | string;
  status: LeadStatus | string;
  stage: Stage;
  score: number | null;
  assigned_to: string | null;
  assigned_name: string | null;
  consent_given: boolean;
  consent_at: string | null;
  created_at: string;
  updated_at: string;
  last_call_at: string | null;
  next_booking_at: string | null;
}

export interface LeadInput {
  name: string;
  phone: string;
  email?: string;
  product_or_course: string;
  notes?: string;
  consent_given: boolean;
  consent_text?: string;
}

export interface LeadNote {
  id: string;
  lead_id: string;
  author_id: string | null;
  author_name: string | null;
  body: string;
  created_at: string;
}

export type EventKind =
  | "lead_created"
  | "call_started"
  | "call_ended"
  | "booking_created"
  | "booking_updated"
  | "whatsapp_sent"
  | "whatsapp_failed"
  | "stage_changed"
  | "assigned"
  | "note_added"
  | "callback_noted";

export interface LeadEvent {
  id: string;
  lead_id: string;
  kind: EventKind | string;
  data: Record<string, unknown>;
  actor_name: string | null;
  created_at: string;
}

export interface LeadDetail {
  lead: Lead;
  calls: CallDetail[];
  bookings: Booking[];
  notes: LeadNote[];
  events: LeadEvent[];
}

export interface Page<T> {
  items: T[];
  total: number;
}

// ---------------------------------------------------------------------------
// Calls
// ---------------------------------------------------------------------------

export type CallStatus = "queued" | "ringing" | "in-progress" | "completed" | "failed" | "no-answer" | "busy";

export interface Call {
  id: string;
  lead_id: string;
  lead_name: string;
  lead_phone: string;
  status: CallStatus | string;
  transport: "browser" | "phone";
  started_at: string | null;
  ended_at: string | null;
  duration_seconds: number | null;
  error: string | null;
  summary: string | null;
  score: number | null;
  intent: string | null;
  extraction: Record<string, unknown> | null;
  turns: number;
  created_at: string;
}

export interface Turn {
  role: "user" | "assistant";
  text: string;
  at: string | null;
  interrupted?: boolean;
}

export interface CallDetail extends Call {
  transcript: Turn[];
}

/** What the public form and "call again" get back. */
export interface LeadCreateResponse {
  lead: Lead;
  call: Call | null;
  call_skipped_reason: string | null;
}

// ---------------------------------------------------------------------------
// Bookings
// ---------------------------------------------------------------------------

export type BookingStatus = "booked" | "cancelled" | "completed" | "no_show";
export type WhatsAppStatus = "pending" | "sent" | "failed" | "skipped";

export interface Booking {
  id: string;
  lead_id: string;
  lead_name: string;
  lead_phone: string;
  call_id: string | null;
  counsellor_id: string | null;
  counsellor_name: string | null;
  scheduled_at: string;
  timezone: string;
  duration_minutes: number;
  requested_text: string | null;
  notes: string | null;
  meeting_provider: string | null;
  meeting_url: string | null;
  meeting_error: string | null;
  whatsapp_status: WhatsAppStatus;
  whatsapp_error: string | null;
  whatsapp_sent_at: string | null;
  status: BookingStatus;
  created_at: string;
}

export interface Availability {
  date: string;
  slots: string[];
  taken: string[];
  slot_minutes: number;
  timezone: string;
}

export interface BookingInput {
  lead_id: string;
  counsellor_id: string;
  date: string;
  time: string;
  mode: "video" | "phone";
  notes?: string;
}

// ---------------------------------------------------------------------------
// Dashboard and analytics
// ---------------------------------------------------------------------------

export interface DashboardSummary {
  scope: "all" | "mine";
  counts: {
    leads: number;
    qualified: number;
    appointments_today: number;
    converted: number;
    calls_today: number;
  };
  queue: Lead[];
  today: Booking[];
}

export interface AnalyticsSummary {
  total: number;
  converted: number;
  conversion_rate: number;
  funnel: { stage: Stage; n: number }[];
  sources: { source: string; n: number }[];
  calls: { status: string; n: number }[];
  top_source: string | null;
}

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------

export interface VoiceSettings {
  agent_name: string;
  company: string;
  flow: string;
  languages: string[];
  greeting_language: string;
  tts_model: string;
  tts_speaker: string;
  llm_provider: string;
  llm_model: string;
  counsellor_hours: string;
  booking_timezone: string;
  meeting_provider: string;
  whatsapp_template: string;
  call_transport: string;
  agent_reported_at: string | null;
}

export interface Health {
  status: string;
  database: string;
  [key: string]: string;
}

/** Public status the form page polls while the phone rings. */
export interface CallStatusResponse {
  call: {
    id: string;
    lead_id: string;
    status: CallStatus | string;
    transport: "browser" | "phone";
    error: string | null;
    started_at: string | null;
    ended_at: string | null;
    created_at: string;
  };
  turns: number;
  summary: string | null;
}
