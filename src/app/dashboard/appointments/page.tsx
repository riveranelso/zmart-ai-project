import { isGhlConfigured, getAppointments } from "@/lib/gohighlevel";
import { EmptyState } from "@/components/dashboard/EmptyState";
import { PageHeader } from "@/components/dashboard/PageHeader";
import { Card } from "@/components/dashboard/Card";
import { Badge } from "@/components/dashboard/Badge";

export default async function AppointmentsPage() {
  if (!isGhlConfigured()) {
    return (
      <div>
        <PageHeader title="Citas" />
        <EmptyState message="Conecta GoHighLevel para ver tus citas." />
      </div>
    );
  }

  const appointments = await getAppointments();

  return (
    <div>
      <PageHeader title="Citas" />
      {appointments.length === 0 ? (
        <EmptyState message="No hay citas próximas." />
      ) : (
        <Card>
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-neutral-200 text-xs uppercase tracking-wide text-neutral-500 dark:border-neutral-800 dark:text-neutral-400">
                <th className="pb-3 font-medium">Título</th>
                <th className="pb-3 font-medium">Inicio</th>
                <th className="pb-3 font-medium">Fin</th>
                <th className="pb-3 font-medium">Estado</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
              {appointments.map((appointment) => (
                <tr
                  key={appointment.id}
                  className="hover:bg-neutral-50 dark:hover:bg-neutral-800/60"
                >
                  <td className="py-3">{appointment.title}</td>
                  <td className="py-3 text-neutral-600 dark:text-neutral-400">
                    {new Date(appointment.startTime).toLocaleString()}
                  </td>
                  <td className="py-3 text-neutral-600 dark:text-neutral-400">
                    {new Date(appointment.endTime).toLocaleString()}
                  </td>
                  <td className="py-3">
                    <Badge status={appointment.appointmentStatus} />
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
