-- Veredictos del agente de corroboracion de leads
-- Tabla destino del script supabase/tools/corroborate_leads.py
-- Sin PII: solo estructura. Los veredictos con telefonos reales NO se commitean.

create table if not exists public.lead_verification (
  phone text primary key,
  verdict text not null check (verdict in ('consistente','dudoso','descartable')),
  reasons text,
  checked_at timestamptz not null default now()
);

create index if not exists lead_verification_verdict_idx on public.lead_verification (verdict);

-- Vista util: leads consistentes con datos del contacto y del telefono
create or replace view public.leads_verificados as
select v.phone, v.verdict, v.reasons,
       c.full_name, c.email, c.stage,
       e.carrier, e.line_type, e.location
from public.lead_verification v
left join public.hl_contacts c on c.phone = v.phone
left join public.phone_enrichment e on e.phone = v.phone;
