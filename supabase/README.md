# Supabase — Zmart 360

Migración de contactos de HighLevel a Supabase. Proyecto destino: **zmart-360** (región Americas, org ZMART 360).

## Estructura

```
supabase/
  migrations/
    20261004070000_create_hl_contacts.sql   # esquema: tabla public.hl_contacts + índices
  README.md                                 # este archivo
```

## Procedimiento de importación (cuando el proyecto exista)

1. **Crear el proyecto** en el dashboard de Supabase:
   - Organization: ZMART 360
   - Name: `zmart-360`
   - Database password: (la defines tú, no se versiona)
   - Region: Americas
   - Espera a que termine el provisioning.

2. **Aplicar el esquema**: en el proyecto, abre **SQL Editor → New query**,
   pega el contenido de `migrations/20261004070000_create_hl_contacts.sql` y dale **Run**.
   (Alternativa con Supabase CLI: `supabase db push` con el repo vinculado.)

3. **Cargar los datos**: el seed con las 47 filas **NO está en git**
   (contiene PII real de contactos y este repo es público).
   Se entrega por separado como `002_seed_hl_contacts.sql`:
   pégalo en el SQL Editor y dale **Run**.

4. **Verificar**:
   ```sql
   select count(*) from public.hl_contacts;                       -- esperado: 47
   select lead_quality, count(*) from public.hl_contacts
     group by 1 order by 1;                                       -- real 33, test 10, duplicate 3, sample 1
   select full_name, duplicate_of_name from public.hl_contacts
     where lead_quality = 'duplicate';                            -- 3 filas, cada una apunta a su original
   ```

## Enriquecimiento de teléfonos (NumVerify)

El script `supabase/tools/enrich_phones.py` valida los teléfonos de los leads
y guarda compañía, tipo de línea y ubicación en `public.phone_enrichment`.

```bash
# 1. API key gratis (100/mes) desde numverify.com — nunca hardcodear ni commitear
export NUMVERIFY_API_KEY=tu_key

# 2. Correr (usa caché local .enrich_cache.json para no gastar cuota)
python3 supabase/tools/enrich_phones.py \
  --input highlevel_contacts_clean.csv \
  --out /tmp/enriched.csv \
  --sql /tmp/enrich.sql

# 3. Aplicar migración de la tabla (una vez por proyecto)
#    SQL Editor -> supabase/migrations/20261004073000_create_phone_enrichment.sql -> Run

# 4. Cargar resultados
#    SQL Editor -> /tmp/enrich.sql -> Run   (NO commitear: contiene teléfonos reales)
```

La vista `public.phones_whatsapp_ok` lista los móviles válidos con su contacto.

## Agente de corroboración

El script `supabase/tools/corroborate_leads.py` cruza los datos de NumVerify
y emite un veredicto por lead (determinístico, sin LLM):

- **consistente**: móvil válido, compañía de PR
- **dudoso**: línea fija/VoIP, sin compañía, o ubicación del número que no
  coincide con el pueblo del lead (si el CSV trae columna `town`/`municipality`)
- **descartable**: número inválido

```bash
python3 supabase/tools/corroborate_leads.py \
  --enriched /tmp/enriched.csv \
  --contacts highlevel_contacts_clean.csv \
  --out /tmp/verificacion.csv \
  --sql /tmp/verificacion.sql
# SQL Editor -> /tmp/verificacion.sql -> Run   (NO commitear: contiene teléfonos)
```

La vista `public.leads_verificados` une veredicto + contacto + datos del teléfono.

## Reglas

- Nunca versionar: password de la base de datos, `service_role` key, `anon` key ni ningún secreto.
- Las 47 filas originales no se modifican ni se eliminan; los duplicados se marcan,
  nunca se borran, y conservan la referencia a su registro original.
- No hay deploy automático: vincular este repo en Supabase (GitHub integration)
  aplica las migraciones con cada push — hacerlo solo cuando el seed y el esquema
  estén aprobados.
- No tocar ZION ni el tráfico actual de Zmart.

## Origen de los datos

Export CSV de HighLevel (LeadConnector), 2026-10-04. 47 filas:
33 reales (14 Qualified / 19 Intake), 10 test, 3 duplicadas, 1 sample.
Archivo fuente y análisis: fuera de git, en el workspace local (`zmart-migration/`).
