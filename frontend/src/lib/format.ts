/**
 * Dates, durations and phone numbers, the way they read on screen.
 * Everything is shown in India time regardless of the viewer's clock.
 */

export const TZ = "Asia/Kolkata";

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit", hour12: true, timeZone: TZ });
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: TZ });
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "";
  return `${fmtDate(iso)}, ${fmtTime(iso)}`;
}

/** "3m ago", "2h ago", "4d ago". */
export function relative(iso: string | null | undefined): string {
  if (!iso) return "";
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const h = Math.round(mins / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.round(h / 24);
  return d < 30 ? `${d}d ago` : fmtDate(iso);
}

/** Seconds to m:ss. */
export function fmtDuration(seconds: number | null | undefined): string {
  if (!seconds && seconds !== 0) return "";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

/** Today, Tomorrow, Yesterday, or the date, in India time. */
export function dayLabel(iso: string): string {
  const key = (d: Date) => d.toLocaleDateString("en-CA", { timeZone: TZ });
  const target = key(new Date(iso));
  const now = new Date();
  if (target === key(now)) return "Today";
  if (target === key(new Date(now.getTime() + 86400000))) return "Tomorrow";
  if (target === key(new Date(now.getTime() - 86400000))) return "Yesterday";
  return fmtDate(iso);
}

/** YYYY-MM-DD for a date in India time. */
export function isoDay(d: Date): string {
  return d.toLocaleDateString("en-CA", { timeZone: TZ });
}

export function initials(name: string): string {
  return name
    .split(" ")
    .filter(Boolean)
    .map((n) => n[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}
