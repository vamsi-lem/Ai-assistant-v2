"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Search, CornerDownLeft } from "lucide-react";
import { useLeads } from "@/components/providers/LeadsProvider";
import { stageLabel, temperature } from "@/lib/labels";

/** Searches the leads already loaded for this user: name, phone, course, email. */
export function GlobalSearch() {
  const router = useRouter();
  const { leads } = useLeads();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onClick = (e: MouseEvent) => { if (wrap.current && !wrap.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const term = q.trim().toLowerCase();
  const digits = term.replace(/\D/g, "");
  const results = term.length
    ? leads.filter((l) =>
        l.name.toLowerCase().includes(term) ||
        (digits.length >= 3 && l.phone.replace(/\D/g, "").includes(digits)) ||
        l.product_or_course.toLowerCase().includes(term) ||
        (l.email ?? "").toLowerCase().includes(term),
      ).slice(0, 6)
    : [];

  function go(id: string) { setOpen(false); setQ(""); router.push(`/leads/${id}`); }

  return (
    <div ref={wrap} className="relative max-w-md flex-1">
      <form onSubmit={(e) => { e.preventDefault(); if (results[0]) go(results[0].id); }}>
        <div className="flex items-center gap-2 rounded-full border border-line bg-panel px-3.5 py-2 text-[13px]">
          <Search className="h-4 w-4 text-mut" />
          <input
            value={q}
            onChange={(e) => { setQ(e.target.value); setOpen(true); }}
            onFocus={() => setOpen(true)}
            placeholder="Search leads by name, phone, course"
            className="w-full bg-transparent text-ink placeholder:text-mut outline-none"
          />
        </div>
      </form>

      {open && term.length > 0 && (
        <div className="absolute left-0 right-0 top-full z-50 mt-2 overflow-hidden rounded-xl border border-line bg-bg-2 shadow-2xl">
          {results.length === 0 ? (
            <p className="px-4 py-6 text-center text-[13px] text-mut">No leads found</p>
          ) : (
            <ul className="max-h-80 overflow-y-auto py-1">
              {results.map((l) => (
                <li key={l.id}>
                  <button onClick={() => go(l.id)} className="flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left hover:bg-panel">
                    <span className="min-w-0">
                      <span className="block truncate text-[13px] font-semibold">{l.name}</span>
                      <span className="block truncate text-[11px] text-mut">{l.phone} · {l.product_or_course}</span>
                    </span>
                    <span className="shrink-0 rounded-full bg-white/10 px-2 py-0.5 text-[10px] text-soft">
                      {stageLabel(l.stage)} · {temperature(l.score)}
                    </span>
                  </button>
                </li>
              ))}
              <li className="flex items-center gap-1.5 border-t border-line px-4 py-2 text-[11px] text-mut">
                <CornerDownLeft className="h-3 w-3" /> Enter opens the first result
              </li>
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
