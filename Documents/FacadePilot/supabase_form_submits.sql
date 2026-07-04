-- FacadePilot form submits
-- Apply before publishing landing pages that use the repaired contact flow.
-- The browser anon key may insert homeowner-provided contact details, but may
-- not select/update/delete them. Follow-up should use service-role backend code.

create table if not exists public.form_submits (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  capakey text not null,
  niscode text,
  source text,
  naam text not null,
  telefoon text not null,
  email text not null,
  opmerking text,
  consent boolean not null default false,
  page_url text,
  user_agent text,
  processed_at timestamptz,
  processed_by text,
  status text not null default 'new'
);

alter table public.form_submits enable row level security;

drop policy if exists "form_submits_anon_insert" on public.form_submits;
create policy "form_submits_anon_insert"
on public.form_submits
for insert
to anon
with check (
  capakey is not null
  and naam is not null
  and telefoon is not null
  and email is not null
  and consent is true
);

drop policy if exists "form_submits_no_anon_read" on public.form_submits;
create policy "form_submits_no_anon_read"
on public.form_submits
for select
to anon
using (false);

create index if not exists form_submits_capakey_idx on public.form_submits (capakey);
create index if not exists form_submits_status_created_idx on public.form_submits (status, created_at desc);
