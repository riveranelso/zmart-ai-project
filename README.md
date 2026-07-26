# Zmart AI

Agentes de voz con IA para negocios. Zmart AI usa **GoHighLevel (GHL)** como
sistema de datos: contactos, llamadas, citas y pipeline de leads. Este
repositorio es el sitio web + dashboard que consulta esos datos.

Construido con Next.js, TypeScript y Tailwind CSS. Sin base de datos propia:
GoHighLevel es la fuente de verdad.

## Estructura del proyecto

```
src/
  app/
    page.tsx              # Landing page pública
    dashboard/
      layout.tsx           # Shell con sidebar
      page.tsx              # Overview
      contacts/page.tsx     # Contactos (GHL Contacts API)
      calls/page.tsx         # Llamadas (GHL Conversations API)
      appointments/page.tsx  # Citas (GHL Calendars API)
      leads/page.tsx         # Leads / pipeline (GHL Opportunities API)
  lib/
    gohighlevel.ts         # Cliente de la API de GoHighLevel
  components/
    dashboard/
      Sidebar.tsx
      EmptyState.tsx
```

## Setup

1. Instalar dependencias:
   ```bash
   npm install
   ```
2. Copiar `.env.example` a `.env` y completar las credenciales de GoHighLevel:
   ```bash
   cp .env.example .env
   ```
   - `GHL_API_KEY`: token de una Private Integration en GoHighLevel (Settings
     → Private Integrations) con acceso a Contacts, Calendars, Opportunities
     y Conversations.
   - `GHL_LOCATION_ID`: ID de la sub-cuenta (location) de GoHighLevel.
3. Levantar el servidor de desarrollo:
   ```bash
   npm run dev
   ```

Sin credenciales configuradas, el dashboard muestra un estado vacío en cada
sección en vez de fallar.

La app queda disponible en `http://localhost:3000` (landing) y
`http://localhost:3000/dashboard`.

## Pendiente / siguientes pasos

- Probar y ajustar `src/lib/gohighlevel.ts` contra la API real de
  GoHighLevel (los nombres de campos pueden variar según la versión).
- Autenticación para el dashboard (hoy es de acceso libre).
- Soporte multi-location si Zmart AI atiende a más de un negocio con la
  misma instancia.
