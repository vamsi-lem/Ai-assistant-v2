"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Brand } from "@/components/layout/Brand";
import { authConfigured, AUTH_NOT_CONFIGURED, hasSession, setPassword } from "@/lib/api/session";

/**
 * Where an invitation or a password reset link lands. Supabase puts a short
 * lived session in the link; the user chooses a password and goes to the
 * dashboard.
 */
export default function SetPasswordPage() {
  const router = useRouter();
  const [ready, setReady] = useState<"checking" | "ok" | "expired">("checking");
  const [p1, setP1] = useState("");
  const [p2, setP2] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!authConfigured()) {
      setError(AUTH_NOT_CONFIGURED);
      setReady("expired");
      return;
    }
    // The client needs a moment to read the session out of the URL hash.
    const t = setTimeout(() => {
      hasSession().then((yes) => setReady(yes ? "ok" : "expired"));
    }, 400);
    return () => clearTimeout(t);
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (p1.length < 8) return setError("Use at least 8 characters.");
    if (p1 !== p2) return setError("The two passwords do not match.");
    setBusy(true);
    setError(null);
    const err = await setPassword(p1);
    setBusy(false);
    if (err) return setError(err);
    router.replace("/dashboard");
  }

  return (
    <main className="grid min-h-screen place-items-center p-6">
      <div className="w-full max-w-[380px]">
        <Brand className="mb-8" href="/login" />
        <h1 className="text-[26px] font-extrabold tracking-[-0.02em]">Choose a password</h1>

        {ready === "checking" && <p className="mt-3 text-[13.5px] text-soft">Checking your link.</p>}

        {ready === "expired" && (
          <div className="mt-3 space-y-3">
            <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-[12.5px] text-red-300">
              {error ?? "This link has expired or was already used. Ask your admin for a new invitation, or request a reset from the sign in page."}
            </p>
            <button onClick={() => router.push("/login")} className="text-[13px] text-violet-2 hover:underline">Go to sign in</button>
          </div>
        )}

        {ready === "ok" && (
          <form onSubmit={submit} className="mt-6 space-y-3.5">
            <label className="block">
              <span className="mb-1.5 block text-[12px] font-medium text-soft">New password</span>
              <input type="password" value={p1} onChange={(e) => setP1(e.target.value)} autoComplete="new-password" className="w-full rounded-xl border border-line bg-bg-2 px-3.5 py-2.5 text-[14px] text-ink outline-none focus:border-line-2" />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-[12px] font-medium text-soft">Repeat it</span>
              <input type="password" value={p2} onChange={(e) => setP2(e.target.value)} autoComplete="new-password" className="w-full rounded-xl border border-line bg-bg-2 px-3.5 py-2.5 text-[14px] text-ink outline-none focus:border-line-2" />
            </label>
            {error && <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-[12.5px] text-red-300">{error}</p>}
            <button type="submit" disabled={busy} className="w-full rounded-full bg-ink py-3 text-[14px] font-semibold text-[#0a0a0d] disabled:opacity-50">
              {busy ? "Saving" : "Save and continue"}
            </button>
          </form>
        )}
      </div>
    </main>
  );
}
