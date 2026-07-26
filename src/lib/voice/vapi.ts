import type { NextRequest } from "next/server";

export function isValidVapiWebhook(req: NextRequest): boolean {
  const secret = req.headers.get("x-vapi-secret");
  return Boolean(secret) && secret === process.env.VAPI_WEBHOOK_SECRET;
}

export interface VapiCallEndedEvent {
  type: "call.ended";
  call: {
    id: string;
    type?: string;
    customer?: { number?: string; name?: string };
    metadata?: { companyId?: string };
    transcript?: string;
    durationSeconds?: number;
    startedAt?: string;
    endedAt?: string;
  };
}
