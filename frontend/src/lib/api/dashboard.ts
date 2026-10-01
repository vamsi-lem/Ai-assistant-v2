/**
 * Dashboard and analytics numbers, computed by the backend in one query each.
 *
 * Backend: backend/app/routers/dashboard.py
 */

import { request } from "@/lib/api/client";
import type { AnalyticsSummary, DashboardSummary, Health } from "@/lib/types";

export function getDashboard(): Promise<DashboardSummary> {
  return request<DashboardSummary>("/dashboard/summary");
}

export function getAnalytics(): Promise<AnalyticsSummary> {
  return request<AnalyticsSummary>("/analytics/summary");
}

/** Public. Used by the form footer to say whether the backend is up. */
export function getHealth(): Promise<Health> {
  return request<Health>("/health", { auth: false });
}
