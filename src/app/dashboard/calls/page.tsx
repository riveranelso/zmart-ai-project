import { isGhlConfigured, getConversations } from "@/lib/gohighlevel";
import { EmptyState } from "@/components/dashboard/EmptyState";
import { PageHeader } from "@/components/dashboard/PageHeader";
import { Card } from "@/components/dashboard/Card";

export default async function CallsPage() {
  if (!isGhlConfigured()) {
    return (
      <div>
        <PageHeader title="Llamadas" />
        <EmptyState message="Conecta GoHighLevel para ver tus llamadas." />
      </div>
    );
  }

  const conversations = await getConversations();

  return (
    <div>
      <PageHeader title="Llamadas" />
      {conversations.length === 0 ? (
        <EmptyState message="No hay llamadas todavía." />
      ) : (
        <Card>
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-neutral-200 text-xs uppercase tracking-wide text-neutral-500 dark:border-neutral-800 dark:text-neutral-400">
                <th className="pb-3 font-medium">Contacto</th>
                <th className="pb-3 font-medium">Último mensaje</th>
                <th className="pb-3 font-medium">Tipo</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
              {conversations.map((conversation) => (
                <tr
                  key={conversation.id}
                  className="hover:bg-neutral-50 dark:hover:bg-neutral-800/60"
                >
                  <td className="py-3">{conversation.contactId ?? "—"}</td>
                  <td className="py-3 text-neutral-600 dark:text-neutral-400">
                    {conversation.lastMessageBody ?? "—"}
                  </td>
                  <td className="py-3 text-neutral-600 dark:text-neutral-400">
                    {conversation.lastMessageType ?? "—"}
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
