import {
  LayoutDashboard,
  Users,
  Inbox,
  CalendarDays,
  AudioLines,
  BarChart3,
  Settings,
  type LucideIcon,
} from "lucide-react";
import type { Permission } from "@/lib/rbac";

export type NavItem = { href: string; label: string; icon: LucideIcon; perm?: Permission };

export const navItems: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/leads", label: "Leads", icon: Users },
  { href: "/leads/incoming", label: "Incoming", icon: Inbox, perm: "leads:assign" },
  { href: "/calls", label: "Calls", icon: AudioLines },
  { href: "/appointments", label: "Appointments", icon: CalendarDays },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/settings", label: "Settings", icon: Settings, perm: "console:view" },
];

/** Longest prefix match so nested routes do not light up their parent. */
export function activeHref(pathname: string, items: NavItem[]): string | undefined {
  return items
    .filter((it) => pathname === it.href || pathname.startsWith(it.href + "/"))
    .sort((a, b) => b.href.length - a.href.length)[0]?.href;
}
