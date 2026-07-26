import { Users, CalendarDays, Target } from "lucide-react";
import {
  isGhlConfigured,
  getContacts,
  getAppointments,
  getOpportunities,
} from "@/lib/gohighlevel";
import { EmptyState } from "@/components/dashboard/EmptyState";
import { PageHeader } from "@/components/dashboard/PageHeader";
import { StatCard } from "@/components/dashboard/StatCard";

export default async function DashboardPage() {
  if (!isGhlConfigured()) {
    return (
      <div>
        <PageHeader title="Overview" />
        <EmptyState message="Conecta GoHighLevel (GHL_API_KEY y GHL_LOCATION_ID) para ver tus datos aquí." />
      </div>
    );
  }

  const [contacts, appointments, opportunities] = await Promise.all([
    getContacts(),
    getAppointments(),
    getOpportunities(),
  ]);

  const stats = [
    { label: "Contactos", value: contacts.length, icon: Users },
    { label: "Citas próximas", value: appointments.length, icon: CalendarDays },
    { label: "Oportunidades", value: opportunities.length, icon: Target },
  ];

  return (
    <div>
      <PageHeader
        title="Overview"
        description="Resumen de tu cuenta de GoHighLevel."
      />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {stats.map((stat) => (
          <StatCard key={stat.label} {...stat} />
        ))}
      </div>
    </div>
  );
}
