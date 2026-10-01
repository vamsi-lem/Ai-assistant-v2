"use client";

import { useState } from "react";
import { Eyebrow } from "@/components/ui/Card";
import { RequirePerm } from "@/components/auth/Gate";
import { TeamPanel } from "@/components/settings/TeamPanel";
import { VoicePanel } from "@/components/settings/VoicePanel";
import { cn } from "@/lib/utils/cn";

const TABS = [
  { id: "team", label: "Team and roles" },
  { id: "voice", label: "Voice AI" },
] as const;
type TabId = (typeof TABS)[number]["id"];

export default function SettingsPage() {
  const [tab, setTab] = useState<TabId>("team");
  return (
    <RequirePerm perm="console:view" message="Settings are available to admins and managers.">
      <div className="space-y-5">
        <div>
          <Eyebrow>Settings</Eyebrow>
          <h1 className="mt-1.5 text-[24px] font-extrabold tracking-[-0.02em]">Organisation</h1>
        </div>
        <div className="grid grid-cols-1 gap-5 md:grid-cols-[210px_1fr]">
          <div className="flex gap-1 md:sticky md:top-[78px] md:flex-col md:self-start">
            {TABS.map((t) => (
              <button key={t.id} onClick={() => setTab(t.id)} className={cn(
                "rounded-lg border px-3 py-2.5 text-left text-[13.5px] font-medium transition-colors",
                tab === t.id ? "border-line bg-panel-2 text-ink" : "border-transparent text-soft hover:bg-panel hover:text-ink",
              )}>{t.label}</button>
            ))}
          </div>
          <div className="min-w-0 space-y-4">
            {tab === "team" && <TeamPanel />}
            {tab === "voice" && <VoicePanel />}
          </div>
        </div>
      </div>
    </RequirePerm>
  );
}
