import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { isValidVapiWebhook, type VapiCallEndedEvent } from "@/lib/voice/vapi";
import { qualifyLead } from "@/lib/qualifyLead";

export async function POST(req: NextRequest) {
  if (!isValidVapiWebhook(req)) {
    return NextResponse.json({ error: "Firma inválida" }, { status: 401 });
  }

  const event = await req.json();

  if (event.type !== "call.ended") {
    return NextResponse.json({ received: true });
  }

  const { call } = event as VapiCallEndedEvent;
  const companyId = call.metadata?.companyId;

  if (!companyId) {
    return NextResponse.json(
      { error: "companyId requerido en metadata de la llamada" },
      { status: 400 },
    );
  }

  const phone = call.customer?.number;
  const transcript = call.transcript ?? "";
  const qualification = transcript ? await qualifyLead(transcript) : null;

  let lead = phone
    ? await prisma.lead.findFirst({ where: { companyId, phone } })
    : null;

  if (!lead) {
    lead = await prisma.lead.create({
      data: {
        companyId,
        phone,
        name: call.customer?.name,
        status: qualification?.status ?? "NEW",
        score: qualification?.score,
        summary: qualification?.summary,
      },
    });
  } else if (qualification) {
    lead = await prisma.lead.update({
      where: { id: lead.id },
      data: {
        status: qualification.status,
        score: qualification.score,
        summary: qualification.summary,
      },
    });
  }

  await prisma.call.create({
    data: {
      companyId,
      leadId: lead.id,
      externalId: call.id,
      direction: call.type === "outboundPhoneCall" ? "OUTBOUND" : "INBOUND",
      transcript,
      durationSec: call.durationSeconds,
      startedAt: call.startedAt ? new Date(call.startedAt) : undefined,
      endedAt: call.endedAt ? new Date(call.endedAt) : undefined,
    },
  });

  return NextResponse.json({ received: true, leadId: lead.id });
}
