"use client";

import { ShieldAlert } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { useCan } from "@/components/providers/RoleProvider";
import type { Permission } from "@/lib/rbac";

/** Renders children only if the current role holds the permission. */
export function Gate({
  perm,
  children,
  fallback = null,
}: {
  perm: Permission;
  children: React.ReactNode;
  fallback?: React.ReactNode;
}) {
  return useCan(perm) ? <>{children}</> : <>{fallback}</>;
}

/** Full page guard: shows an "access denied" card when the role lacks the permission. */
export function RequirePerm({
  perm,
  children,
  message = "This area is available to admins and managers.",
}: {
  perm: Permission;
  children: React.ReactNode;
  message?: string;
}) {
  if (useCan(perm)) return <>{children}</>;
  return (
    <Card className="mx-auto mt-10 max-w-md text-center">
      <ShieldAlert className="mx-auto h-8 w-8 text-mut" />
      <h1 className="mt-3 text-[18px] font-bold">Access restricted</h1>
      <p className="mt-1 text-[13px] text-soft">{message}</p>
    </Card>
  );
}
