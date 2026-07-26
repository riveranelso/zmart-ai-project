import { isGhlConfigured, getContacts } from "@/lib/gohighlevel";
import { EmptyState } from "@/components/dashboard/EmptyState";
import { PageHeader } from "@/components/dashboard/PageHeader";
import { Card } from "@/components/dashboard/Card";

export default async function ContactsPage() {
  if (!isGhlConfigured()) {
    return (
      <div>
        <PageHeader title="Contactos" />
        <EmptyState message="Conecta GoHighLevel para ver tus contactos." />
      </div>
    );
  }

  const contacts = await getContacts();

  return (
    <div>
      <PageHeader title="Contactos" />
      {contacts.length === 0 ? (
        <EmptyState message="No hay contactos todavía." />
      ) : (
        <Card>
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-neutral-200 text-xs uppercase tracking-wide text-neutral-500 dark:border-neutral-800 dark:text-neutral-400">
                <th className="pb-3 font-medium">Nombre</th>
                <th className="pb-3 font-medium">Teléfono</th>
                <th className="pb-3 font-medium">Email</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
              {contacts.map((contact) => (
                <tr
                  key={contact.id}
                  className="hover:bg-neutral-50 dark:hover:bg-neutral-800/60"
                >
                  <td className="py-3">
                    {[contact.firstName, contact.lastName].filter(Boolean).join(" ") || "—"}
                  </td>
                  <td className="py-3 text-neutral-600 dark:text-neutral-400">
                    {contact.phone ?? "—"}
                  </td>
                  <td className="py-3 text-neutral-600 dark:text-neutral-400">
                    {contact.email ?? "—"}
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
