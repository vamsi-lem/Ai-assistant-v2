"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { can as canFn, roleLabel, type Permission } from "@/lib/rbac";
import { getMe } from "@/lib/api/team";
import { ApiError } from "@/lib/api/client";
import { signOutToLogin } from "@/lib/api/session";
import type { Profile, Role } from "@/lib/types";

interface RoleCtx {
  profile: Profile;
  role: Role;
  user: { name: string; title: string; email: string };
  userId: string;
  can: (perm: Permission) => boolean;
}

const Ctx = createContext<RoleCtx>(null as unknown as RoleCtx);

/**
 * Who is signed in, according to the backend. The role comes from the
 * profiles table, never from the browser, so a user cannot promote themselves.
 */
export function RoleProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getMe()
      .then(setProfile)
      .catch((err: unknown) => {
        // 401 is handled inside the API client (sign out, back to /login with
        // the reason). Everything else, including 403, is shown here.
        if (err instanceof ApiError && err.status === 401) return;
        setError(err instanceof Error ? err.message : "Could not load your profile.");
      });
  }, [router]);

  async function backToLogin() {
    await signOutToLogin();
  }

  if (error) {
    return (
      <div className="grid min-h-screen place-items-center p-6">
        <div className="max-w-md rounded-2xl border border-red-500/30 bg-red-500/[0.06] p-5 text-[13.5px]">
          <p className="font-semibold text-red-300">Could not load your profile</p>
          <pre className="mt-2 whitespace-pre-wrap font-mono text-[12px] text-soft">{error}</pre>
          <div className="mt-4 flex gap-2">
            <button onClick={() => location.reload()} className="rounded-full border border-line-2 bg-panel px-4 py-2 text-[13px] text-soft hover:text-ink">Try again</button>
            <button onClick={backToLogin} className="rounded-full border border-line-2 bg-panel px-4 py-2 text-[13px] text-soft hover:text-ink">Sign out</button>
          </div>
        </div>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="grid min-h-screen place-items-center">
        <span className="h-6 w-6 animate-spin rounded-full border-2 border-line border-t-violet-2" />
      </div>
    );
  }

  return (
    <Ctx.Provider
      value={{
        profile,
        role: profile.role,
        user: { name: profile.name, title: roleLabel(profile.role), email: profile.email },
        userId: profile.id,
        can: (p: Permission) => canFn(profile.role, p),
      }}
    >
      {children}
    </Ctx.Provider>
  );
}

export const useRole = () => useContext(Ctx);
export const useCan = (perm: Permission) => useContext(Ctx).can(perm);
