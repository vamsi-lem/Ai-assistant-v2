"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ChromeRing } from "@/components/visuals/ChromeRing";
import { Brand } from "@/components/layout/Brand";
import { authConfigured, AUTH_NOT_CONFIGURED, hasSession, requestPasswordReset, signIn } from "@/lib/api/session";

const field =
  "w-full rounded-xl border border-line bg-bg-2 px-3.5 py-2.5 text-[14px] text-ink outline-none transition-colors focus:border-line-2";

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <Login />
    </Suspense>
  );
}

function Login() {
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState<"signin" | "reset">("signin");
  // The form stays hidden until we know nobody is signed in, so a signed in
  // person goes straight to the dashboard without seeing it flash past.
  const [checked, setChecked] = useState(false);

  // Already signed in (for example after a refresh): straight to the dashboard.
  // Arriving with ?reason= means the backend rejected the last session; show why.
  useEffect(() => {
    if (!authConfigured()) {
      setError(AUTH_NOT_CONFIGURED);
      setChecked(true);
      return;
    }
    const reason = params.get("reason");
    if (reason) {
      setError(`Signed out by the backend: ${reason}`);
      setChecked(true);
      return;
    }
    hasSession().then((yes) => {
      if (yes) router.replace("/dashboard");
      else setChecked(true);
    });
  }, [router, params]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setInfo(null);

    if (mode === "reset") {
      const err = await requestPasswordReset(email.trim());
      setBusy(false);
      if (err) setError(err);
      else setInfo(`If ${email.trim()} has an account, a password reset link is on its way.`);
      return;
    }

    const err = await signIn(email.trim(), password);
    if (err) {
      setError(err);
      setBusy(false);
      return;
    }
    // A full page load, not a client side hop, so the dashboard starts from
    // nothing and loads this person's profile and leads fresh.
    window.location.assign("/dashboard");
  }

  if (!checked) {
    return (
      <main className="grid min-h-screen place-items-center">
        <span className="h-6 w-6 animate-spin rounded-full border-2 border-line border-t-violet-2" />
      </main>
    );
  }

  return (
    <main className="grid min-h-screen grid-cols-1 lg:grid-cols-2">
      <div className="relative hidden items-center justify-center overflow-hidden border-r border-line p-12 lg:flex">
        <div className="relative z-10 text-center">
          <ChromeRing className="mx-auto block aspect-square w-[300px]" />
          <h2 className="mt-8 text-[26px] font-extrabold tracking-[-0.03em]">
            Every enquiry <span className="text-gradient">answered in seconds.</span>
          </h2>
          <p className="mx-auto mt-3 max-w-[38ch] text-[14px] text-soft">
            Maya calls each new lead, books the counselling slot, and writes the whole conversation here.
          </p>
        </div>
      </div>

      <div className="flex items-center justify-center p-6">
        <div className="w-full max-w-[380px]">
          <Brand className="mb-8" />

          <h1 className="text-[26px] font-extrabold tracking-[-0.02em]">
            {mode === "signin" ? "Sign in" : "Reset password"}
          </h1>
          <p className="mt-1 text-[13.5px] text-soft">
            {mode === "signin"
              ? "Use the email your admin invited."
              : "We will email you a link to choose a new password."}
          </p>

          <form onSubmit={submit} className="mt-6 space-y-3.5">
            <label className="block">
              <span className="mb-1.5 block text-[12px] font-medium text-soft">Email</span>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                className={field}
              />
            </label>

            {mode === "signin" && (
              <label className="block">
                <span className="mb-1.5 block text-[12px] font-medium text-soft">Password</span>
                <input
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  className={field}
                />
              </label>
            )}

            {error && (
              <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-[12.5px] text-red-300">{error}</p>
            )}
            {info && (
              <p className="rounded-lg border border-emerald-400/30 bg-emerald-400/10 px-3 py-2 text-[12.5px] text-emerald-300">{info}</p>
            )}

            <button
              type="submit"
              disabled={busy || !authConfigured()}
              className="mt-2 w-full rounded-full bg-ink py-3 text-[14px] font-semibold text-[#0a0a0d] transition-transform hover:-translate-y-0.5 disabled:opacity-50"
            >
              {busy ? "Please wait" : mode === "signin" ? "Sign in" : "Send reset link"}
            </button>
          </form>

          <p className="mt-5 text-center text-[12.5px] text-mut">
            {mode === "signin" ? (
              <button onClick={() => { setMode("reset"); setError(null); setInfo(null); }} className="text-violet-2 hover:underline">
                Forgot your password?
              </button>
            ) : (
              <button onClick={() => { setMode("signin"); setError(null); setInfo(null); }} className="text-violet-2 hover:underline">
                Back to sign in
              </button>
            )}
          </p>
        </div>
      </div>
    </main>
  );
}
