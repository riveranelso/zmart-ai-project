import {
  isGhlConfigured,
  getContacts,
  getAppointments,
  getOpportunities,
} from "@/lib/gohighlevel";
import { EmptyState } from "@/components/dashboard/EmptyState";

export default async function DashboardPage() {
  if (!isGhlConfigured()) {
    return (
      <EmptyState message="Conecta GoHighLevel (GHL_API_KEY y GHL_LOCATION_ID) para ver tus datos aquí." />
    );
  }

  const [contacts, appointments, opportunities] = await Promise.all([
    getContacts(),
    getAppointments(),
    getOpportunities(),
  ]);

  const stats = [
    { label: "Contactos", value: contacts.length },
    { label: "Citas próximas", value: appointments.length },
    { label: "Oportunidades", value: opportunities.length },
  ];

  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold">Overview</h1>
      <div className="grid grid-cols-3 gap-4">
        {stats.map((stat) => (
          <div key={stat.label} className="rounded-lg border border-gray-200 p-6">
            <div className="text-3xl font-bold">{stat.value}</div>
            <div className="text-sm text-gray-500">{stat.label}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
