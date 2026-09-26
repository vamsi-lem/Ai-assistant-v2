/**
 * Shapes shared with the backend.
 *
 * These mirror backend/app/schemas.py. If you change one, change both.
 */

/** Sarvam language codes. Mirrors LanguageCode in backend/app/schemas.py. */
export type LanguageCode =
  | 'hi-IN'
  | 'en-IN'
  | 'te-IN'
  | 'ta-IN'
  | 'kn-IN'
  | 'ml-IN'
  | 'mr-IN'
  | 'bn-IN'
  | 'gu-IN'
  | 'pa-IN'
  | 'od-IN';

export interface LeadInput {
  name: string;
  phone: string;
  email?: string;
  product_or_course: string;
  notes?: string;
  consent_given: boolean;
  consent_text?: string;
}

export interface Lead {
  id: string;
  name: string;
  phone: string;
  email: string | null;
  product_or_course: string;
  notes: string | null;
  preferred_language: LanguageCode;
  callback_time: string | null;
  callback_notes: string | null;
  source: string;
  status: string;
  consent_given: boolean;
  consent_at: string | null;
  created_at: string;
}

export type CallStatus =
  | 'queued'
  | 'ringing'
  | 'in-progress'
  | 'completed'
  | 'failed'
  | 'no-answer'
  | 'busy';

export interface Call {
  id: string;
  lead_id: string;
  status: CallStatus;
  transport: 'browser' | 'phone';
  room_name: string | null;
  provider: string | null;
  provider_call_id: string | null;
  error: string | null;
  started_at: string | null;
  ended_at: string | null;
  created_at: string;
}

/**
 * Present only on the browser path. The token is minted by the backend, scoped
 * to this one room, and valid for thirty minutes. The frontend never holds a
 * LiveKit API key.
 */
export interface BrowserJoin {
  url: string;
  token: string;
  room_name: string;
}

export interface LeadCreateResponse {
  lead: Lead;
  call: Call | null;
  join: BrowserJoin | null;
  /** Set when the lead was saved but no call was placed, and why. */
  call_skipped_reason: string | null;
}

export interface CallStatusResponse {
  call: Call;
  turns: number;
  summary: string | null;
}

/** A turn as the agent recorded it. */
export interface Turn {
  role: 'user' | 'assistant';
  text: string;
  at: string;
  interrupted: boolean;
}

/** One row of the counsellor dashboard. Mirrors BookingRow in schemas.py. */
export interface BookingRow {
  id: string;
  scheduled_at: string;
  timezone: string;
  duration_minutes: number;
  status: 'booked' | 'cancelled' | 'completed' | 'no_show';
  meeting_url: string | null;
  meeting_provider: string | null;
  meeting_error: string | null;
  whatsapp_status: 'pending' | 'sent' | 'failed' | 'skipped';
  whatsapp_error: string | null;
  requested_text: string | null;
  notes: string | null;
  lead_id: string;
  lead_name: string;
  lead_phone: string;
  lead_email: string | null;
  product_or_course: string;
  call_id: string | null;
  created_at: string;
}

/** A booking as the backend returns it after an update. */
export interface Booking {
  id: string;
  lead_id: string;
  call_id: string | null;
  scheduled_at: string;
  timezone: string;
  duration_minutes: number;
  requested_text: string | null;
  notes: string | null;
  meeting_provider: string | null;
  meeting_url: string | null;
  meeting_error: string | null;
  whatsapp_status: 'pending' | 'sent' | 'failed' | 'skipped';
  whatsapp_error: string | null;
  status: 'booked' | 'cancelled' | 'completed' | 'no_show';
  created_at: string;
}
