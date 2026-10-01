"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { authConfigured, currentUserId, onAuthChange } from "@/lib/api/session";

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
  const [ok, setOk] = useState(false);
  const userId = useRef<string | null>(null);

  useEffect(() => {
    if (!authConfigured()) {
      router.replace("/login");
      return;
    }
    currentUserId().then((id) => {
      if (id) {
        userId.current = id;
        setOk(true);
      } else {
        router.replace("/login");
      }
    });
    return onAuthChange((id) => {
      if (!id) {
        router.replace("/login");
      } else if (userId.current && id !== userId.current) {
        window.location.reload();
      } else {
        userId.current = id;
      }
    });
  }, [router]);

  if (!ok) {
    return (
      <div className="grid min-h-screen place-items-center">
        <span className="h-6 w-6 animate-spin rounded-full border-2 border-line border-t-violet-2" />
      </div>
    );
  }
  return <>{children}</>;
}
