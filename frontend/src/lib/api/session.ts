/**
 * Sign in, sign out, and the current token.
 *
 * Supabase Auth holds the accounts. The browser talks to Supabase for exactly
 * one thing: exchanging an email and password for a token. That token then
 * goes to our backend on every request, and the backend decides what the
 * user may see. The browser never reads a table directly.
 *
 * The anon key used here is Supabase's public browser key. It is meant to be
 * shipped in a frontend and, with row level security on, cannot read a row.
 */

import { createClient, type Session, type SupabaseClient } from "@supabase/supabase-js";

const URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
const ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

let client: SupabaseClient | null = null;

/** True when both Supabase values are present in .env.local. */
export function authConfigured(): boolean {
  return URL.startsWith("http") && ANON_KEY.length > 20;
}

export const AUTH_NOT_CONFIGURED =
  "Sign in is not configured. Put NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY in frontend/.env.local and restart npm run dev.";

function supabase(): SupabaseClient {
  if (!client) {
    if (!authConfigured()) throw new Error(AUTH_NOT_CONFIGURED);
    client = createClient(URL, ANON_KEY, {
      auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
    });
  }
  return client;
}

/** Access token for the backend, or null when nobody is signed in. */
export async function getAccessToken(): Promise<string | null> {
  if (!authConfigured()) return null;
  const { data } = await supabase().auth.getSession();
  return data.session?.access_token ?? null;
}

/** Email and password sign in. Returns an error message, or null on success. */
export async function signIn(email: string, password: string): Promise<string | null> {
  if (!authConfigured()) return AUTH_NOT_CONFIGURED;
  const { error } = await supabase().auth.signInWithPassword({ email, password });
  if (!error) return null;
  if (/failed to fetch|networkerror|load failed/i.test(error.message)) {
    return `Could not reach Supabase from your browser (${URL}). Check the connection and NEXT_PUBLIC_SUPABASE_URL, then try again.`;
  }
  if (/invalid login credentials/i.test(error.message)) return "Wrong email or password.";
  if (/email not confirmed/i.test(error.message)) return "This email has not been confirmed yet. Open the link in the invitation email first.";
  return error.message;
}

/**
 * Signs out and makes sure nothing of the old session is left in the browser.
 *
 * A global sign out asks Supabase to revoke the refresh token too. If that
 * call fails (connection drop, Supabase busy) supabase-js keeps the local
 * session, which is exactly the "sign out, sign in as someone else, still
 * treated as the first person" problem. So on any failure fall back to a
 * local sign out, and as a last resort clear the stored keys by hand.
 */
export async function signOut(): Promise<void> {
  if (!authConfigured()) return;
  try {
    const { error } = await supabase().auth.signOut({ scope: "global" });
    if (error) await supabase().auth.signOut({ scope: "local" });
  } catch {
    try {
      await supabase().auth.signOut({ scope: "local" });
    } catch {
      // Fall through to the manual cleanup below.
    }
  }
  if (typeof window !== "undefined") {
    try {
      Object.keys(window.localStorage)
        .filter((key) => key.startsWith("sb-"))
        .forEach((key) => window.localStorage.removeItem(key));
    } catch {
      // Storage blocked (private mode); nothing was persisted in the first place.
    }
  }
}

/** Signs out, then does a full page load of /login so no screen keeps the old person's data. */
export async function signOutToLogin(reason?: string): Promise<void> {
  await signOut();
  if (typeof window !== "undefined") {
    window.location.assign(reason ? `/login?reason=${encodeURIComponent(reason)}` : "/login");
  }
}

/** The signed in user's id, or null. */
export async function currentUserId(): Promise<string | null> {
  if (!authConfigured()) return null;
  const { data } = await supabase().auth.getSession();
  return data.session?.user.id ?? null;
}

/** Sends the password reset email. Returns an error message, or null. */
export async function requestPasswordReset(email: string): Promise<string | null> {
  if (!authConfigured()) return AUTH_NOT_CONFIGURED;
  const redirectTo = typeof window !== "undefined" ? `${window.location.origin}/set-password` : undefined;
  const { error } = await supabase().auth.resetPasswordForEmail(email, { redirectTo });
  return error ? error.message : null;
}

/**
 * Sets the password for the user who arrived through an invitation or a
 * reset link. Supabase puts a session in the URL; the client picks it up on
 * page load, so by the time this runs the user is signed in.
 */
export async function setPassword(password: string): Promise<string | null> {
  if (!authConfigured()) return AUTH_NOT_CONFIGURED;
  const { data } = await supabase().auth.getSession();
  if (!data.session) return "This link has expired or was already used. Ask an admin to send a new invitation.";
  const { error } = await supabase().auth.updateUser({ password });
  return error ? error.message : null;
}

/** Waits for Supabase to finish reading a session from the URL or storage. */
export async function hasSession(): Promise<boolean> {
  if (!authConfigured()) return false;
  const { data } = await supabase().auth.getSession();
  return !!data.session;
}

/**
 * Runs `fn` whenever the auth state changes: sign out or sign in from another
 * tab, token refresh. `userId` is null when nobody is signed in.
 */
export function onAuthChange(fn: (userId: string | null) => void): () => void {
  if (!authConfigured()) return () => {};
  const { data } = supabase().auth.onAuthStateChange((_event: string, session: Session | null) =>
    fn(session?.user.id ?? null),
  );
  return () => data.subscription.unsubscribe();
}
