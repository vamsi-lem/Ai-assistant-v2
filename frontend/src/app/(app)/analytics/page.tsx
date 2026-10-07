"use client";

import { Card, Eyebrow } from "@/components/ui/Card";
import { Spinner, ErrorCard, Empty } from "@/components/ui/State";
import { useRole } from "@/components/providers/RoleProvider";
import { getAnalytics } from "@/lib/api/dashboard";
import { useCached } from "@/lib/hooks/useCached";
import { callStatusLabel, sourceLabel, stageLabel } from "@/lib/labels";

export default function AnalyticsPage() {
  const { can } = useRole();
  const scopedAll = can("leads:viewAll");
  const { data: a, error, loading, reload: load } = useCached("analytics", getAnalytics, "Could not load analytics.");

  const funnelMax = Math.max(1, ...(a?.funnel.map((f) => f.n) ?? [1]));
  const sourceTotal = Math.max(1, a?.total ?? 1);
  const callTotal = Math.max(1, a?.calls.reduce((s, c) => s + c.n, 0) ?? 1);

  return (
    <div className="space-y-5">
      <div>
        <Eyebrow>Funnel and sources</Eyebrow>
        <h1 className="mt-1.5 text-[24px] font-extrabold tracking-[-0.02em]">Analytics</h1>
        <p className="mt-1 text-[12.5px] text-mut">{scopedAll ? "Across all account leads." : "Across the leads assigned to you."}</p>
      </div>

      {error && <ErrorCard message={error} onRetry={load} />}
      {loading && !error && <Spinner />}
      {a && a.total === 0 && <Empty>No leads yet. Analytics appear once the first lead arrives.</Empty>}

      {a && a.total > 0 && (
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
          <Card>
            <h2 className="text-[15px] font-bold">Pipeline by stage</h2>
            <div className="mt-4 space-y-2.5">
              {a.funnel.map((f) => (
                <div key={f.stage} className="flex items-center gap-3 text-[13px]">
                  <span className="w-28 text-soft">{stageLabel(f.stage)}</span>
                  <span className="h-4 flex-1 overflow-hidden rounded-md bg-white/5">
                    <span
                      className={`block h-full rounded-md ${f.stage === "converted" ? "bg-emerald-400" : f.stage === "lost" ? "bg-white/20" : "[background:linear-gradient(90deg,var(--violet),var(--violet-2))]"}`}
                      style={{ width: `${Math.round((f.n / funnelMax) * 100)}%` }}
                    />
                  </span>
                  <span className="w-8 text-right font-semibold">{f.n}</span>
                </div>
              ))}
            </div>
            <div className="mt-4 grid grid-cols-2 gap-3">
              <div className="rounded-xl border border-line bg-panel p-3">
                <p className="font-mono text-[10px] uppercase text-mut">Conversion rate</p>
                <p className="text-gradient text-[22px] font-extrabold">{a.conversion_rate}%</p>
              </div>
              <div className="rounded-xl border border-line bg-panel p-3">
                <p className="font-mono text-[10px] uppercase text-mut">Top source</p>
                <p className="text-[22px] font-extrabold">{a.top_source ? sourceLabel(a.top_source) : "n/a"}</p>
              </div>
            </div>
          </Card>

          <div className="space-y-5">
            <Card>
              <h2 className="text-[15px] font-bold">Lead sources</h2>
              <div className="mt-4 space-y-3">
                {a.sources.map((s) => {
                  const pct = Math.round((s.n / sourceTotal) * 100);
                  return (
                    <div key={s.source}>
                      <div className="mb-1 flex justify-between text-[12px]">
                        <span className="text-soft">{sourceLabel(s.source)}</span>
                        <span className="font-semibold">{s.n} · {pct}%</span>
                      </div>
                      <div className="h-2 overflow-hidden rounded-full bg-white/5">
                        <div className="h-full rounded-full [background:linear-gradient(90deg,var(--violet-2),var(--warm))]" style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                  );
                })}
              </div>
              <div className="mt-4 rounded-xl border border-line bg-panel p-3">
                <p className="font-mono text-[10px] uppercase text-mut">Total leads</p>
                <p className="text-[22px] font-extrabold">{a.total}</p>
              </div>
            </Card>

            <Card>
              <h2 className="text-[15px] font-bold">Call outcomes</h2>
              <div className="mt-4 space-y-3">
                {a.calls.map((c) => {
                  const pct = Math.round((c.n / callTotal) * 100);
                  return (
                    <div key={c.status}>
                      <div className="mb-1 flex justify-between text-[12px]">
                        <span className="text-soft">{callStatusLabel(c.status)}</span>
                        <span className="font-semibold">{c.n} · {pct}%</span>
                      </div>
                      <div className="h-2 overflow-hidden rounded-full bg-white/5">
                        <div className={`h-full rounded-full ${c.status === "completed" ? "bg-emerald-400" : c.status === "failed" ? "bg-red-400" : "bg-amber-300"}`} style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                  );
                })}
                {a.calls.length === 0 && <p className="text-[12px] text-mut">No calls yet.</p>}
              </div>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
