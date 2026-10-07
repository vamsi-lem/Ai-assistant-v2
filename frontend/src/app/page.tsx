"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { authConfigured, hasSession } from "@/lib/api/session";

/**
 * The root has no page of its own. The session lives in the browser, so the
 * browser decides: signed in goes straight to the dashboard, anyone else to
 * the sign in page. No login form flashes past on the way.
 */
export default function Home() {
  const router = useRouter();

  useEffect(() => {
    if (!authConfigured()) {
      router.replace("/login");
      return;
    }
    hasSession().then((yes) => router.replace(yes ? "/dashboard" : "/login"));
  }, [router]);

  return (
    <main className="grid min-h-screen place-items-center">
      <span className="h-6 w-6 animate-spin rounded-full border-2 border-line border-t-violet-2" />
    </main>
  );
}
