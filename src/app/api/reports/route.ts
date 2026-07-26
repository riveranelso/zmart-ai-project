import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function GET(req: NextRequest) {
  const companyId = req.nextUrl.searchParams.get("companyId");

  if (!companyId) {
    return NextResponse.json({ error: "companyId requerido" }, { status: 400 });
  }

  const [totalCalls, leadsByStatus] = await Promise.all([
    prisma.call.count({ where: { companyId } }),
    prisma.lead.groupBy({
      by: ["status"],
      where: { companyId },
      _count: true,
    }),
  ]);

  return NextResponse.json({ totalCalls, leadsByStatus });
}
