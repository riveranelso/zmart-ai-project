import { isGhlConfigured, getContacts } from "@/lib/gohighlevel";
import { EmptyState } from "@/components/dashboard/EmptyState";

export default async function ContactsPage() {
  if (!isGhlConfigured()) {
    return <EmptyState message="Conecta GoHighLevel para ver tus contactos." />;
  }

  const contacts = await getContacts();

  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold">Contactos</h1>
      {contacts.length === 0 ? (
        <EmptyState message="No hay contactos todavía." />
      ) : (
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-gray-200">
              <th className="py-2">Nombre</th>
              <th className="py-2">Teléfono</th>
              <th className="py-2">Email</th>
            </tr>
          </thead>
          <tbody>
            {contacts.map((contact) => (
              <tr key={contact.id} className="border-b border-gray-100">
                <td className="py-2">
                  {[contact.firstName, contact.lastName].filter(Boolean).join(" ") || "—"}
                </td>
                <td className="py-2">{contact.phone ?? "—"}</td>
                <td className="py-2">{contact.email ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
