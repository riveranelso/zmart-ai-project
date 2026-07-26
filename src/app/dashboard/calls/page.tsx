import { isGhlConfigured, getConversations } from "@/lib/gohighlevel";
import { EmptyState } from "@/components/dashboard/EmptyState";

export default async function CallsPage() {
  if (!isGhlConfigured()) {
    return <EmptyState message="Conecta GoHighLevel para ver tus llamadas." />;
  }

  const conversations = await getConversations();

  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold">Llamadas</h1>
      {conversations.length === 0 ? (
        <EmptyState message="No hay llamadas todavía." />
      ) : (
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-gray-200">
              <th className="py-2">Contacto</th>
              <th className="py-2">Último mensaje</th>
              <th className="py-2">Tipo</th>
            </tr>
          </thead>
          <tbody>
            {conversations.map((conversation) => (
              <tr key={conversation.id} className="border-b border-gray-100">
                <td className="py-2">{conversation.contactId ?? "—"}</td>
                <td className="py-2">{conversation.lastMessageBody ?? "—"}</td>
                <td className="py-2">{conversation.lastMessageType ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
