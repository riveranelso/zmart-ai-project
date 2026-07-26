import { isGhlConfigured, getOpportunities } from "@/lib/gohighlevel";
import { EmptyState } from "@/components/dashboard/EmptyState";
import { PageHeader } from "@/components/dashboard/PageHeader";
import { Card } from "@/components/dashboard/Card";
import { Badge } from "@/components/dashboard/Badge";

export default async function LeadsPage() {
  if (!isGhlConfigured()) {
    return (
      <div>
        <PageHeader title="Leads" />
        <EmptyState message="Conecta GoHighLevel para ver tus leads." />
      </div>
    );
  }

  const opportunities = await getOpportunities();

  return (
    <div>
      <PageHeader title="Leads" />
      {opportunities.length === 0 ? (
        <EmptyState message="No hay leads todavía." />
      ) : (
        <Card>
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-neutral-200 text-xs uppercase tracking-wide text-neutral-500 dark:border-neutral-800 dark:text-neutral-400">
                <th className="pb-3 font-medium">Nombre</th>
                <th className="pb-3 font-medium">Etapa</th>
                <th className="pb-3 font-medium">Estado</th>
                <th className="pb-3 font-medium">Valor</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
              {opportunities.map((opportunity) => (
                <tr
                  key={opportunity.id}
                  className="hover:bg-neutral-50 dark:hover:bg-neutral-800/60"
                >
                  <td className="py-3">{opportunity.name}</td>
                  <td className="py-3 text-neutral-600 dark:text-neutral-400">
                    {opportunity.pipelineStageId ?? "—"}
                  </td>
                  <td className="py-3">
                    <Badge status={opportunity.status} />
                  </td>
                  <td className="py-3 text-neutral-600 dark:text-neutral-400">
                    {opportunity.monetaryValue != null
                      ? `$${opportunity.monetaryValue}`
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
