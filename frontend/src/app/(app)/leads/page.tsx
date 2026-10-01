"use client";

import { useState } from "react";
import { Eyebrow } from "@/components/ui/Card";
import { Spinner, ErrorCard } from "@/components/ui/State";
import { KanbanBoard } from "@/components/leads/KanbanBoard";
import { AddLeadModal } from "@/components/leads/AddLeadModal";
import { useRole } from "@/components/providers/RoleProvider";
import { useLeads } from "@/components/providers/LeadsProvider";
import { cn } from "@/lib/utils/cn";

export default function LeadsPage() {
  const { can } = useRole();
  const { leads, loading, error, refresh } = useLeads();
  const canEdit = can("leads:edit");
  const scopedAll = can("leads:viewAll");
  const [showLost, setShowLost] = useState(false);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <Eyebrow>{scopedAll ? "All account leads" : "Your assigned leads"}</Eyebrow>
          <h1 className="mt-1.5 text-[24px] font-extrabold tracking-[-0.02em]">Lead pipeline</h1>
          {canEdit && <p className="mt-1 text-[12.5px] text-mut">Drag a card between columns to change its stage. Maya sets the call outcome; the stage is yours.</p>}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowLost((v) => !v)}
            className={cn("rounded-full border px-3.5 py-2 text-[12.5px]", showLost ? "border-line-2 bg-panel-2 text-ink" : "border-line bg-panel text-soft hover:text-ink")}
          >
            {showLost ? "Hide lost" : "Show lost"}
          </button>
          {canEdit && <AddLeadModal />}
        </div>
      </div>

      {error && <ErrorCard message={error} onRetry={refresh} />}
      {loading && !error && <Spinner />}
      {!loading && !error && <KanbanBoard leads={leads} editable={canEdit} showLost={showLost} />}
    </div>
  );
}
