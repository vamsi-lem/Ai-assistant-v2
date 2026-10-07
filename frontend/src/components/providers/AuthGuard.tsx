"use client";

import { createContext, useContext, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { authConfigured, currentUserId, onAuthChange } from "@/lib/api/session";

const SessionCtx = createContext<string>("");

/** The signed in user's id (from the token, before the profile has loaded). */
export const useSessionUserId = () => useContext(SessionCtx);

/**
 * Bounces to /login when nobody is signed in.
 *
 * The session lives in the browser's storage, so every tab of this browser
 * is the same person. If another tab signs out, this one goes to /login; if
 * another tab signs in as a different person, this one reloads so it shows
 * that person's data instead of a mix of two.
 */
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [userId, setUserId] = useState<string>("");
  const known = useRef<string | null>(null);

  useEffect(() => {
    if (!authConfigured()) {
      router.replace("/login");
      return;
    }
    currentUserId().then((id) => {
      if (id) {
        known.current = id;
        setUserId(id);
      } else {
        router.replace("/login");
      }
    });
    return onAuthChange((id) => {
      if (!id) {
        router.replace("/login");
      } else if (known.current && id !== known.current) {
        window.location.reload();
      } else {
        known.current = id;
      }
    });
  }, [router]);

  if (!userId) {
    return (
      <div className="grid min-h-screen place-items-center">
        <span className="h-6 w-6 animate-spin rounded-full border-2 border-line border-t-violet-2" />
      </div>
    );
  }
  return <SessionCtx.Provider value={userId}>{children}</SessionCtx.Provider>;
}
