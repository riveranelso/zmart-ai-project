# Zmart AI

SaaS de agente de IA construido con Next.js, TypeScript y el SDK de Anthropic.

## Estructura del proyecto

```
src/
  app/            # Rutas (App Router)
    api/chat/     # Endpoint del agente de IA
    page.tsx      # Landing page
  components/     # Componentes UI
  lib/
    anthropic.ts  # Cliente de la API de Anthropic
```

## Setup

1. Instalar dependencias:
   ```bash
   npm install
   ```
2. Copiar `.env.example` a `.env` y completar `ANTHROPIC_API_KEY`:
   ```bash
   cp .env.example .env
   ```
3. Levantar el servidor de desarrollo:
   ```bash
   npm run dev
   ```

La app queda disponible en `http://localhost:3000`.
