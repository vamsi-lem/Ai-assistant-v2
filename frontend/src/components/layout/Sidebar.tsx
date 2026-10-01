"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LogOut, ExternalLink } from "lucide-react";
import { cn } from "@/lib/utils/cn";
import { useRole } from "@/components/providers/RoleProvider";
import { navItems, activeHref } from "@/components/layout/nav-items";
import { Brand } from "@/components/layout/Brand";
import { signOutToLogin } from "@/lib/api/session";

export function Sidebar() {
  const pathname = usePathname();
  const { user, can } = useRole();
  const visible = navItems.filter((it) => !it.perm || can(it.perm));
  const active = activeHref(pathname, visible);

  async function logout() {
    await signOutToLogin();
  }

  return (
    <aside className="hidden w-[232px] shrink-0 flex-col border-r border-line px-3 py-5 md:flex">
      <Brand size="sm" className="mb-6 px-2" />
      <nav className="flex flex-col gap-1">
        {visible.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex items-center gap-3 rounded-xl border px-3 py-2.5 text-[14px] font-medium transition-colors",
              href === active ? "border-line bg-panel-2 text-ink" : "border-transparent text-soft hover:bg-panel hover:text-ink",
            )}
          >
            <Icon className="h-[18px] w-[18px]" strokeWidth={href === active ? 2 : 1.7} />
            {label}
          </Link>
        ))}
      </nav>
      <Link href="/form" target="_blank" rel="noreferrer" className="mt-4 flex items-center gap-2 rounded-xl px-3 py-2 text-[12.5px] text-mut hover:text-ink">
        <ExternalLink className="h-3.5 w-3.5" /> Open the lead form
      </Link>
      <div className="mt-auto rounded-xl border border-line bg-panel p-3 text-[12px] text-soft">
        <p className="font-mono text-[10px] uppercase tracking-wide text-mut">Signed in</p>
        <p className="mt-1 font-semibold text-ink">{user.name}</p>
        <p className="text-[11px] text-mut">{user.title}</p>
        <button onClick={logout} className="mt-2.5 flex w-full items-center gap-2 rounded-lg border border-line px-2.5 py-1.5 text-[12px] text-soft hover:border-line-2 hover:text-ink">
          <LogOut className="h-3.5 w-3.5" /> Sign out
        </button>
      </div>
    </aside>
  );
}
