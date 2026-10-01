/**
 * Read only view of how the agent is configured. Editing arrives with the
 * tenants table (docs/MULTI-TENANT.md).
 *
 * Backend: backend/app/routers/settings.py
 */

import { request } from "@/lib/api/client";
import type { VoiceSettings } from "@/lib/types";

export function getVoiceSettings(): Promise<VoiceSettings> {
  return request<VoiceSettings>("/settings/voice");
}
