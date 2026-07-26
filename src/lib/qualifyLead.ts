import { anthropic } from "@/lib/anthropic";

export interface LeadQualification {
  status: "QUALIFIED" | "DISQUALIFIED";
  score: number;
  summary: string;
}

export async function qualifyLead(transcript: string): Promise<LeadQualification> {
  const response = await anthropic.messages.create({
    model: "claude-sonnet-5",
    max_tokens: 500,
    messages: [
      {
        role: "user",
        content: `Analiza esta transcripción de una llamada y determina si el lead está calificado.

Transcripción:
${transcript}

Responde Únicamente con un JSON con este formato exacto, sin texto adicional:
{"status": "QUALIFIED" | "DISQUALIFIED", "score": <número 0-100>, "summary": "<resumen breve>"}`,
      },
    ],
  });

  const textBlock = response.content.find((block) => block.type === "text");
  const parsed = JSON.parse(textBlock?.type === "text" ? textBlock.text : "{}");

  return {
    status: parsed.status === "QUALIFIED" ? "QUALIFIED" : "DISQUALIFIED",
    score: typeof parsed.score === "number" ? parsed.score : 0,
    summary: typeof parsed.summary === "string" ? parsed.summary : "",
  };
}
