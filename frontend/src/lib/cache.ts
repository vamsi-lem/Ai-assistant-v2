/**
 * Last known data, kept in the browser so a screen can paint at once.
 *
 * Every dashboard screen shows what it showed last time the moment it opens,
 * then asks the backend for the current data and swaps it in. The first
 * visit of the day therefore looks like every other visit, instead of a
 * spinner while the token refreshes, the backend wakes and the queries run.
 *
 * Entries are keyed by the signed in user's id, so two people sharing one
 * browser never see each other's data, and `clearCache` runs on sign out.
 * This is a convenience, never the source of truth: the backend is always
 * asked, and what it answers replaces what was cached.
 */

const PREFIX = "maya:";
const MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000; // older than a week is not worth painting

interface Entry<T> {
  at: number;
  value: T;
}

function storage(): Storage | null {
  try {
    return typeof window !== "undefined" ? window.localStorage : null;
  } catch {
    return null; // private mode or storage blocked
  }
}

export function readCache<T>(userId: string, key: string): T | null {
  const store = storage();
  if (!store) return null;
  try {
    const raw = store.getItem(`${PREFIX}${userId}:${key}`);
    if (!raw) return null;
    const entry = JSON.parse(raw) as Entry<T>;
    if (!entry || typeof entry.at !== "number" || Date.now() - entry.at > MAX_AGE_MS) return null;
    return entry.value;
  } catch {
    return null;
  }
}

export function writeCache<T>(userId: string, key: string, value: T): void {
  const store = storage();
  if (!store) return;
  try {
    const entry: Entry<T> = { at: Date.now(), value };
    store.setItem(`${PREFIX}${userId}:${key}`, JSON.stringify(entry));
  } catch {
    // Quota full or storage blocked. The screen still works, it just will not paint early next time.
  }
}

/** Drops every cached screen. Called on sign out. */
export function clearCache(): void {
  const store = storage();
  if (!store) return;
  try {
    Object.keys(store)
      .filter((k) => k.startsWith(PREFIX))
      .forEach((k) => store.removeItem(k));
  } catch {
    // Nothing to clear.
  }
}
