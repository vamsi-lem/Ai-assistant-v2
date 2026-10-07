"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useSessionUserId } from "@/components/providers/AuthGuard";
import { ApiError } from "@/lib/api/client";
import { readCache, writeCache } from "@/lib/cache";

interface Cached<T> {
  /** Last known data (from the cache) or fresh data (from the backend). */
  data: T | null;
  /** True until the first answer from the backend in this visit. */
  loading: boolean;
  /** True while `data` is the cached copy and the backend has not answered yet. */
  stale: boolean;
  error: string | null;
  reload: () => void;
}

/**
 * Paint the last known answer at once, then fetch the current one.
 *
 *   const { data, loading, error, reload } = useCached("dashboard", getDashboard);
 *
 * `key` names the screen (and its filter, when it has one). `fetcher` must be
 * stable across renders: wrap it in useCallback when it closes over state.
 */
export function useCached<T>(key: string, fetcher: () => Promise<T>, fallbackMessage = "Could not load."): Cached<T> {
  const userId = useSessionUserId();
  const [data, setData] = useState<T | null>(() => (userId ? readCache<T>(userId, key) : null));
  const [stale, setStale] = useState<boolean>(data !== null);
  const [loading, setLoading] = useState<boolean>(data === null);
  const [error, setError] = useState<string | null>(null);
  const run = useRef(0);

  const reload = useCallback(() => {
    const id = ++run.current;
    setError(null);
    fetcher()
      .then((fresh) => {
        if (id !== run.current) return; // a newer request took over
        setData(fresh);
        setStale(false);
        setLoading(false);
        if (userId) writeCache(userId, key, fresh);
      })
      .catch((err: unknown) => {
        if (id !== run.current) return;
        setLoading(false);
        setError(err instanceof ApiError ? err.message : err instanceof Error ? err.message : fallbackMessage);
      });
  }, [fetcher, key, userId, fallbackMessage]);

  // Key changed (a filter, say): swap in that key's cached copy, then refresh.
  useEffect(() => {
    const cached = userId ? readCache<T>(userId, key) : null;
    setData(cached);
    setStale(cached !== null);
    setLoading(cached === null);
    reload();
  }, [key, userId, reload]);

  return { data, loading, stale, error, reload };
}
