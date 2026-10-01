"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { Menu, X, LogOut } from "lucide-react";
import { cn } from "@/lib/utils/cn";
import { useRole } from "@/components/providers/RoleProvider";
import { navItems, activeHref } from "@/components/layout/nav-items";
import { Brand } from "@/components/layout/Brand";
import { signOutToLogin } from "@/lib/api/session";

export function MobileNav() {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const { user, can } = useRole();
  const visible = navItems.filter((it) => !it.perm || can(it.perm));
  const active = activeHref(pathname, visible);

  async function logout() {
    setOpen(false);
    await signOutToLogin();
  }

  return (
    <>
      <button onClick={() => setOpen(true)} aria-label="Open menu" className="grid h-9 w-9 place-items-center rounded-full border border-line bg-panel text-soft md:hidden">
        <Menu className="h-[18px] w-[18px]" />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div className="fixed inset-0 z-50 md:hidden" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setOpen(false)} />
            <motion.aside
              className="absolute left-0 top-0 flex h-full w-[260px] flex-col border-r border-line bg-bg-2 px-3 py-5"
              initial={{ x: -280 }} animate={{ x: 0 }} exit={{ x: -280 }}
              transition={{ type: "spring", stiffness: 360, damping: 34 }}
            >
              <div className="mb-6 flex items-center justify-between px-2">
                <span onClick={() => setOpen(false)}><Brand size="sm" /></span>
                <button onClick={() => setOpen(false)} aria-label="Close menu" className="text-mut hover:text-ink"><X className="h-5 w-5" /></button>
              </div>
              <nav className="flex flex-col gap-1">
                {visible.map(({ href, label, icon: Icon }) => (
                  <Link
                    key={href}
                    href={href}
                    onClick={() => setOpen(false)}
                    className={cn(
                      "flex items-center gap-3 rounded-xl border px-3 py-2.5 text-[14px] font-medium",
                      href === active ? "border-line bg-panel-2 text-ink" : "border-transparent text-soft hover:bg-panel hover:text-ink",
                    )}
                  >
                    <Icon className="h-[18px] w-[18px]" /> {label}
                  </Link>
                ))}
              </nav>
              <div className="mt-auto rounded-xl border border-line bg-panel p-3 text-[12px] text-soft">
                <p className="font-semibold text-ink">{user.name}</p>
                <p className="text-[11px] text-mut">{user.title}</p>
                <button onClick={logout} className="mt-2.5 flex w-full items-center gap-2 rounded-lg border border-line px-2.5 py-1.5 text-[12px] text-soft">
                  <LogOut className="h-3.5 w-3.5" /> Sign out
                </button>
              </div>
            </motion.aside>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
