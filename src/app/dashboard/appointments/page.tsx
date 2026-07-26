import { isGhlConfigured, getAppointments } from "@/lib/gohighlevel";
import { EmptyState } from "@/components/dashboard/EmptyState";

export default async function AppointmentsPage() {
  if (!isGhlConfigured()) {
    return <EmptyState message="Conecta GoHighLevel para ver tus citas." />;
  }

  const appointments = await getAppointments();

  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold">Citas</h1>
      {appointments.length === 0 ? (
        <EmptyState message="No hay citas próximas." />
      ) : (
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-gray-200">
              <th className="py-2">Título</th>
              <th className="py-2">Inicio</th>
              <th className="py-2">Fin</th>
              <th className="py-2">Estado</th>
            </tr>
          </thead>
          <tbody>
            {appointments.map((appointment) => (
              <tr key={appointment.id} className="border-b border-gray-100">
                <td className="py-2">{appointment.title}</td>
                <td className="py-2">
                  {new Date(appointment.startTime).toLocaleString()}
                </td>
                <td className="py-2">
                  {new Date(appointment.endTime).toLocaleString()}
                </td>
                <td className="py-2">{appointment.appointmentStatus ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
