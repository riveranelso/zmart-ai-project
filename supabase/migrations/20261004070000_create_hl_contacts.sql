-- Zmart Consumer Rights: HighLevel contacts migration
-- Generated 2026-10-04 from highlevel_contacts_raw.csv (47 rows)
-- Table: public.hl_contacts

create table if not exists public.hl_contacts (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz,
  full_name text,
  email text,
  phone text,
  secondary_phone text,
  whatsapp text,
  source text,
  form text,
  channel text,
  stage text,
  owner text,
  labels text,
  lead_quality text not null default 'real'
    check (lead_quality in ('real','test','sample','duplicate')),
  duplicate_of_name text,
  raw_row jsonb,
  imported_at timestamptz not null default now(),
  import_batch text not null default 'highlevel_csv_2026_10_04'
);

create index if not exists hl_contacts_email_idx on public.hl_contacts (lower(email));
create index if not exists hl_contacts_phone_idx on public.hl_contacts (phone);
create index if not exists hl_contacts_quality_idx on public.hl_contacts (lead_quality);
create index if not exists hl_contacts_stage_idx on public.hl_contacts (stage);
