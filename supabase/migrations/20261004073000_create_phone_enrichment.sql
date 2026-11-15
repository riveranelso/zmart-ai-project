-- Enriquecimiento de telefonos de leads (NumVerify)
-- Tabla destino del script supabase/tools/enrich_phones.py
-- Sin PII: solo estructura. Los resultados con telefonos reales NO se commitean.

create table if not exists public.phone_enrichment (
  phone text primary key,
  valid boolean,
  number_e164 text,
  country_code text,
  country_name text,
  location text,
  carrier text,
  line_type text,
  checked_at timestamptz not null default now(),
  source text not null default 'numverify'
);

create index if not exists phone_enrichment_valid_idx on public.phone_enrichment (valid);
create index if not exists phone_enrichment_line_type_idx on public.phone_enrichment (line_type);
create index if not exists phone_enrichment_carrier_idx on public.phone_enrichment (carrier);

-- Vista util: telefonos aptos para WhatsApp/llamada (moviles validos)
create or replace view public.phones_whatsapp_ok as
select e.phone, c.full_name, c.email, e.carrier, e.location
from public.phone_enrichment e
left join public.hl_contacts c on c.phone = e.phone
where e.valid is true and e.line_type = 'mobile';
