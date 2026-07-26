const GHL_BASE_URL = "https://services.leadconnectorhq.com";
const GHL_API_VERSION = "2021-07-28";

export function isGhlConfigured(): boolean {
  return Boolean(process.env.GHL_API_KEY && process.env.GHL_LOCATION_ID);
}

async function ghlFetch<T>(
  path: string,
  params: Record<string, string> = {},
): Promise<T> {
  const url = new URL(GHL_BASE_URL + path);
  Object.entries(params).forEach(([key, value]) => url.searchParams.set(key, value));

  const res = await fetch(url, {
    headers: {
      Authorization: `Bearer ${process.env.GHL_API_KEY}`,
      Version: GHL_API_VERSION,
      Accept: "application/json",
    },
    cache: "no-store",
  });

  if (!res.ok) {
    throw new Error(`GoHighLevel API error (${res.status}) on ${path}`);
  }

  return res.json();
}

export interface GhlContact {
  id: string;
  firstName?: string;
  lastName?: string;
  email?: string;
  phone?: string;
  tags?: string[];
}

export async function getContacts(): Promise<GhlContact[]> {
  const data = await ghlFetch<{ contacts: GhlContact[] }>("/contacts/", {
    locationId: process.env.GHL_LOCATION_ID!,
  });
  return data.contacts ?? [];
}

export interface GhlAppointment {
  id: string;
  title: string;
  startTime: string;
  endTime: string;
  contactId?: string;
  appointmentStatus?: string;
}

export async function getAppointments(): Promise<GhlAppointment[]> {
  const now = new Date();
  const in30Days = new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000);

  const data = await ghlFetch<{ events: GhlAppointment[] }>("/calendars/events", {
    locationId: process.env.GHL_LOCATION_ID!,
    startTime: now.toISOString(),
    endTime: in30Days.toISOString(),
  });
  return data.events ?? [];
}

export interface GhlOpportunity {
  id: string;
  name: string;
  pipelineStageId?: string;
  status?: string;
  monetaryValue?: number;
  contactId?: string;
}

export async function getOpportunities(): Promise<GhlOpportunity[]> {
  const data = await ghlFetch<{ opportunities: GhlOpportunity[] }>(
    "/opportunities/search",
    { location_id: process.env.GHL_LOCATION_ID! },
  );
  return data.opportunities ?? [];
}

export interface GhlConversation {
  id: string;
  contactId?: string;
  lastMessageBody?: string;
  lastMessageType?: string;
  unreadCount?: number;
}

export async function getConversations(): Promise<GhlConversation[]> {
  const data = await ghlFetch<{ conversations: GhlConversation[] }>(
    "/conversations/search",
    { locationId: process.env.GHL_LOCATION_ID! },
  );
  return data.conversations ?? [];
}
