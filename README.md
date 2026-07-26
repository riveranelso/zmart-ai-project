# Zmart AI

Voice AI para compañías: contestación de llamadas, calificación de leads (CRM)
y reportes. Construido con Next.js, TypeScript, Prisma y el SDK de Anthropic.

## Cómo funciona

1. **Vapi** atiende las llamadas entrantes/salientes como agente de voz.
2. Al terminar una llamada, Vapi envía un webhook a `/api/webhooks/vapi`.
3. Zmart AI transcribe la llamada (si no viene ya transcrita), usa Claude
   para calificar al lead (`src/lib/qualifyLead.ts`) y guarda todo en la
   base de datos (`Company`, `Lead`, `Call`).
4. El CRM (`/api/leads`) y los reportes (`/api/reports`) exponen esos datos.

## Estructura del proyecto

```
prisma/
  schema.prisma       # Modelos Company, Lead, Call
src/
  app/
    api/
      webhooks/vapi/   # Recibe eventos de llamadas de Vapi
      leads/           # CRUD de leads (CRM)
      reports/         # Reportes agregados por compañía
    page.tsx           # Landing page
  lib/
    anthropic.ts       # Cliente de la API de Anthropic
    prisma.ts          # Cliente de Prisma
    qualifyLead.ts      # Calificación de leads con Claude
    voice/vapi.ts       # Verificación de webhook y tipos de Vapi
  components/          # Componentes UI
```

## Setup

1. Instalar dependencias:
   ```bash
   npm install
   ```
2. Copiar `.env.example` a `.env` y completar las variables:
   ```bash
   cp .env.example .env
   ```
   - `ANTHROPIC_API_KEY`: clave de Anthropic para calificar leads.
   - `DATABASE_URL`: cadena de conexión a Postgres.
   - `VAPI_WEBHOOK_SECRET`: secreto para validar los webhooks de Vapi.
3. Sincronizar el esquema con la base de datos:
   ```bash
   npm run db:push
   ```
4. Levantar el servidor de desarrollo:
   ```bash
   npm run dev
   ```

La app queda disponible en `http://localhost:3000`.

## Pendiente / siguientes pasos

- Configurar el agente de voz en Vapi y apuntar su webhook a
  `/api/webhooks/vapi` (ajustar el mapeo de campos del payload según la
  API real de Vapi).
- Autenticación y manejo de múltiples compañías (multi-tenant).
- Dashboard del CRM y reportes en el frontend (hoy solo son endpoints).
