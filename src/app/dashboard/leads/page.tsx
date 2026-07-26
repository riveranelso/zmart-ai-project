import { isGhlConfigured, getOpportunities } from "@/lib/gohighlevel";
import { EmptyState } from "@/components/dashboard/EmptyState";

export default async function LeadsPage() {
  if (!isGhlConfigured()) {
    return <EmptyState message="Conecta GoHighLevel para ver tus leads." />;
  }

  const opportunities = await getOpportunities();

  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold">Leads</h1>
      {opportunities.length === 0 ? (
        <EmptyState message="No hay leads todavía." />
      ) : (
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-gray-200">
              <th className="py-2">Nombre</th>
              <th className="py-2">Etapa</th>
              <th className="py-2">Estado</th>
              <th className="py-2">Valor</th>
            </tr>
          </thead>
          <tbody>
            {opportunities.map((opportunity) => (
              <tr key={opportunity.id} className="border-b border-gray-100">
                <td className="py-2">{opportunity.name}</td>
                <td className="py-2">{opportunity.pipelineStageId ?? "—"}</td>
                <td className="py-2">{opportunity.status ?? "—"}</td>
                <td className="py-2">
                  {opportunity.monetaryValue != null
                    ? `$${opportunity.monetaryValue}`
                    : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
