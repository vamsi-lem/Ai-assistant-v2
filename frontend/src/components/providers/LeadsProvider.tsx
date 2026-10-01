"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useToast } from "@/components/providers/ToastProvider";
import * as api from "@/lib/api/leads";
import { listCounsellors } from "@/lib/api/team";
import { ApiError } from "@/lib/api/client";
import type { Lead, Profile, Stage } from "@/lib/types";

interface LeadsCtx {
  leads: Lead[];
  counsellors: Profile[];
  loading: boolean;
  error: string | null;
  setStage: (id: string, stage: Stage) => Promise<void>;
  assign: (ids: string[], counsellorId: string | null) => Promise<void>;
  refresh: () => Promise<void>;
}

const Ctx = createContext<LeadsCtx>(null as unknown as LeadsCtx);

/**
 * The leads the signed in user may see, loaded once and shared by the board,
 * the search box and the queue. The backend applies the role scope, so a
 * counsellor's list already contains only their own leads.
 */
export function LeadsProvider({ children }: { children: React.ReactNode }) {
  const toast = useToast();
  const [leads, setLeads] = useState<Lead[]>([]);
  const [counsellors, setCounsellors] = useState<Profile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [page, team] = await Promise.all([api.listLeads(), listCounsellors()]);
      setLeads(page.items);
      setCounsellors(team);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load leads.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const setStage: LeadsCtx["setStage"] = async (id, stage) => {
    const before = leads;
    setLeads((ls) => ls.map((l) => (l.id === id ? { ...l, stage } : l))); // optimistic
    try {
      await api.setStage(id, stage);
      refresh();
    } catch (err) {
      setLeads(before);
      toast(err instanceof ApiError ? err.message : "Could not change the stage", "error");
    }
  };

  const assign: LeadsCtx["assign"] = async (ids, counsellorId) => {
    try {
      await Promise.all(ids.map((id) => api.assignLead(id, counsellorId)));
      await refresh();
      const who = counsellors.find((c) => c.id === counsellorId)?.name;
      toast(counsellorId ? `${ids.length} lead${ids.length > 1 ? "s" : ""} assigned to ${who ?? "counsellor"}` : "Moved back to the incoming queue", "info");
    } catch (err) {
      toast(err instanceof ApiError ? err.message : "Could not assign", "error");
    }
  };

  return (
    <Ctx.Provider value={{ leads, counsellors, loading, error, setStage, assign, refresh }}>
      {children}
    </Ctx.Provider>
  );
}

export const useLeads = () => useContext(Ctx);
