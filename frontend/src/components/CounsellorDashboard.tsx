/**
 * The counsellor's page: every slot Maya has booked, with the meeting link
 * and whether the WhatsApp confirmation reached the lead.
 *
 * Reached at /#/counsellor. Protected by the dashboard key from
 * backend/.env, typed once and kept in the browser session. This is an
 * internal page for a small team, so a shared key is the right amount of
 * ceremony; the multi-tenant plan replaces it with per-tenant admin keys.
 *
 * Nothing here is decorative. A red WhatsApp status is a task: the lead does
 * not have the link yet, and the resend button is the fix once the cause
 * (usually the template not yet approved) is sorted.
 */

import { useCallback, useEffect, useState } from 'react';

import { ApiError, listBookings, resendWhatsApp, setBookingStatus } from '../api/client';
import type { Booking, BookingRow } from '../types';

const KEY_STORAGE = 'dashboard-key';

function readStoredKey(): string {
  try {
    return sessionStorage.getItem(KEY_STORAGE) ?? '';
  } catch {
    return '';
  }
}

function storeKey(key: string) {
  try {
    if (key) sessionStorage.setItem(KEY_STORAGE, key);
    else sessionStorage.removeItem(KEY_STORAGE);
  } catch {
    /* private mode: the key simply has to be typed again next time */
  }
}

function formatWhen(iso: string, timezone: string): { day: string; time: string } {
  const date = new Date(iso);
  return {
    day: date.toLocaleDateString('en-IN', {
      weekday: 'short',
      day: 'numeric',
      month: 'short',
      timeZone: timezone,
    }),
    time: date.toLocaleTimeString('en-IN', {
      hour: 'numeric',
      minute: '2-digit',
      timeZone: timezone,
    }),
  };
}

function isToday(iso: string, timezone: string): boolean {
  const fmt = (d: Date) => d.toLocaleDateString('en-IN', { timeZone: timezone });
  return fmt(new Date(iso)) === fmt(new Date());
}

export function CounsellorDashboard() {
  const [key, setKey] = useState(readStoredKey);
  const [draftKey, setDraftKey] = useState('');
  const [rows, setRows] = useState<BookingRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [showPast, setShowPast] = useState(false);

  const load = useCallback(async () => {
    if (!key) return;
    setError(null);
    try {
      setRows(await listBookings(key, showPast ? 30 : 1, 60));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setKey('');
        storeKey('');
        setError('That key was not accepted.');
      } else {
        setError(err instanceof ApiError ? err.message : 'Could not load bookings.');
      }
    }
  }, [key, showPast]);

  useEffect(() => {
    void load();
    if (!key) return;
    const timer = window.setInterval(() => void load(), 30_000);
    return () => window.clearInterval(timer);
  }, [key, load]);

  function submitKey(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = draftKey.trim();
    if (!trimmed) return;
    storeKey(trimmed);
    setKey(trimmed);
    setDraftKey('');
  }

  function applyUpdate(updated: Booking) {
    setRows((current) =>
      current
        ? current.map((row) =>
            row.id === updated.id
              ? {
                  ...row,
                  status: updated.status,
                  whatsapp_status: updated.whatsapp_status,
                  whatsapp_error: updated.whatsapp_error,
                  meeting_url: updated.meeting_url,
                }
              : row,
          )
        : current,
    );
  }

  async function resend(id: string) {
    setBusyId(id);
    try {
      applyUpdate(await resendWhatsApp(key, id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Resend failed.');
    } finally {
      setBusyId(null);
    }
  }

  async function mark(id: string, status: Booking['status']) {
    setBusyId(id);
    try {
      applyUpdate(await setBookingStatus(key, id, status));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Update failed.');
    } finally {
      setBusyId(null);
    }
  }

  if (!key) {
    return (
      <form className="card" onSubmit={submitKey}>
        <div className="field">
          <label htmlFor="dashboard-key">Dashboard key</label>
          <input
            id="dashboard-key"
            type="password"
            value={draftKey}
            onChange={(e) => setDraftKey(e.target.value)}
            autoComplete="off"
            autoFocus
          />
          <p className="hint">The DASHBOARD_KEY value from the backend configuration.</p>
        </div>
        {error && (
          <div className="notice notice-bad">
            <p>{error}</p>
          </div>
        )}
        <button type="submit" disabled={!draftKey.trim()}>
          Open dashboard
        </button>
      </form>
    );
  }

  const upcoming = rows?.filter((r) => r.status === 'booked') ?? [];
  const settled = rows?.filter((r) => r.status !== 'booked') ?? [];

  return (
    <div className="dashboard">
      <div className="dash-toolbar">
        <label className="toggle">
          <input type="checkbox" checked={showPast} onChange={(e) => setShowPast(e.target.checked)} />
          Include the last 30 days
        </label>
        <div className="dash-toolbar-actions">
          <button type="button" className="ghost" onClick={() => void load()}>
            Refresh
          </button>
          <button
            type="button"
            className="ghost"
            onClick={() => {
              storeKey('');
              setKey('');
              setRows(null);
            }}
          >
            Lock
          </button>
        </div>
      </div>

      {error && (
        <div className="notice notice-bad">
          <p>{error}</p>
        </div>
      )}

      {rows === null && !error && <p className="hint">Loading bookings...</p>}

      {rows !== null && upcoming.length === 0 && (
        <div className="notice">
          <strong>No upcoming bookings</strong>
          <p>When Maya books a slot on a call it appears here within thirty seconds.</p>
        </div>
      )}

      {upcoming.map((row) => (
        <BookingCard key={row.id} row={row} busy={busyId === row.id} onResend={resend} onMark={mark} />
      ))}

      {settled.length > 0 && (
        <details className="settled">
          <summary>{settled.length} completed, cancelled or missed</summary>
          {settled.map((row) => (
            <BookingCard key={row.id} row={row} busy={busyId === row.id} onResend={resend} onMark={mark} />
          ))}
        </details>
      )}
    </div>
  );
}

interface CardProps {
  row: BookingRow;
  busy: boolean;
  onResend: (id: string) => void;
  onMark: (id: string, status: Booking['status']) => void;
}

function BookingCard({ row, busy, onResend, onMark }: CardProps) {
  const when = formatWhen(row.scheduled_at, row.timezone);
  const today = isToday(row.scheduled_at, row.timezone);
  const waSent = row.whatsapp_status === 'sent';

  return (
    <article className={`card booking ${row.status !== 'booked' ? 'booking-settled' : ''}`}>
      <div className="booking-when">
        <span className={`booking-day ${today ? 'booking-today' : ''}`}>{today ? 'Today' : when.day}</span>
        <span className="booking-time">{when.time}</span>
        <span className="booking-duration">{row.duration_minutes} min</span>
      </div>

      <div className="booking-body">
        <div className="booking-head">
          <h2>{row.lead_name}</h2>
          <span className={`pill pill-${row.status}`}>{row.status.replace('_', ' ')}</span>
        </div>
        <p className="booking-meta">
          {row.product_or_course} &middot;{' '}
          <a href={`tel:${row.lead_phone}`} className="mono">
            {row.lead_phone}
          </a>
          {row.lead_email && (
            <>
              {' '}
              &middot; <a href={`mailto:${row.lead_email}`}>{row.lead_email}</a>
            </>
          )}
        </p>

        {row.requested_text && (
          <p className="booking-quote">Lead said: &ldquo;{row.requested_text}&rdquo;</p>
        )}
        {row.notes && <p className="booking-notes">{row.notes}</p>}

        <div className="booking-status">
          <span className={`pill ${waSent ? 'pill-good' : 'pill-bad'}`}>
            WhatsApp {row.whatsapp_status}
          </span>
          {!waSent && row.whatsapp_error && <span className="booking-error">{row.whatsapp_error}</span>}
          {!row.meeting_url && row.meeting_error && (
            <span className="booking-error">No link: {row.meeting_error}</span>
          )}
        </div>

        <div className="booking-actions">
          {row.meeting_url ? (
            <a className="button-link" href={row.meeting_url} target="_blank" rel="noreferrer">
              Join {row.meeting_provider === 'google' ? 'Google Meet' : 'Zoom'}
            </a>
          ) : (
            <span className="hint">No meeting link. Call the lead on their number.</span>
          )}
          {!waSent && (
            <button type="button" className="ghost" disabled={busy} onClick={() => onResend(row.id)}>
              Resend WhatsApp
            </button>
          )}
          {row.status === 'booked' && (
            <>
              <button type="button" className="ghost" disabled={busy} onClick={() => onMark(row.id, 'completed')}>
                Done
              </button>
              <button type="button" className="ghost" disabled={busy} onClick={() => onMark(row.id, 'no_show')}>
                No show
              </button>
              <button type="button" className="ghost" disabled={busy} onClick={() => onMark(row.id, 'cancelled')}>
                Cancel
              </button>
            </>
          )}
        </div>
      </div>
    </article>
  );
}
