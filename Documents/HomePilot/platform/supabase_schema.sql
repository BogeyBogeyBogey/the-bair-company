-- HomePilot shared property intelligence schema.
-- Apply in Supabase SQL editor or through migrations.

create extension if not exists pgcrypto;

create table if not exists public.homepilot_tenants (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  slug text not null unique,
  subscription_tier text not null default 'pro',
  data_region text not null default 'eu-west',
  settings jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.homepilot_memberships (
  tenant_id uuid not null references public.homepilot_tenants(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null check (role in ('viewer','manager','admin','owner')),
  partner_id text,
  created_at timestamptz not null default now(),
  primary key (tenant_id, user_id)
);

create table if not exists public.homepilot_modules (
  key text primary key,
  label text not null,
  category text not null,
  metric_catalog jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.homepilot_tenant_modules (
  tenant_id uuid not null references public.homepilot_tenants(id) on delete cascade,
  module_key text not null references public.homepilot_modules(key),
  enabled boolean not null default true,
  settings jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  primary key (tenant_id, module_key)
);

create table if not exists public.homepilot_properties (
  id text primary key,
  tenant_id uuid not null references public.homepilot_tenants(id) on delete cascade,
  source_external_id text,
  address text not null,
  postcode text,
  city text,
  country_code text not null default 'BE',
  lat double precision,
  lon double precision,
  property_type text,
  core jsonb not null default '{}'::jsonb,
  tags text[] not null default '{}'::text[],
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.homepilot_property_media (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.homepilot_tenants(id) on delete cascade,
  property_id text not null references public.homepilot_properties(id) on delete cascade,
  module_key text references public.homepilot_modules(key),
  media_type text not null check (media_type in ('streetview','satellite','render','photo','document','other')),
  url text,
  storage_path text,
  metadata jsonb not null default '{}'::jsonb,
  captured_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists public.homepilot_campaigns (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.homepilot_tenants(id) on delete cascade,
  module_key text not null references public.homepilot_modules(key),
  name text not null,
  channel text not null default 'direct_mail',
  status text not null default 'draft' check (status in ('draft','running','paused','completed','archived')),
  territory jsonb not null default '{}'::jsonb,
  message_variant text,
  partner_id text,
  partner_name text,
  metadata jsonb not null default '{}'::jsonb,
  started_at timestamptz,
  ended_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.homepilot_campaign_targets (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.homepilot_tenants(id) on delete cascade,
  campaign_id uuid not null references public.homepilot_campaigns(id) on delete cascade,
  property_id text not null references public.homepilot_properties(id) on delete cascade,
  module_key text not null references public.homepilot_modules(key),
  status text not null default 'generated' check (status in (
    'generated','queued','sent','scanned','clicked','responded','appointment','customer','rejected','no_response'
  )),
  priority_score numeric,
  priority_grade text,
  assigned_to uuid references auth.users(id),
  last_interaction_at timestamptz,
  next_action_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (campaign_id, property_id, module_key)
);

create table if not exists public.homepilot_assessments (
  id text primary key,
  tenant_id uuid not null references public.homepilot_tenants(id) on delete cascade,
  property_id text not null references public.homepilot_properties(id) on delete cascade,
  module_key text not null references public.homepilot_modules(key),
  score numeric,
  grade text,
  confidence numeric,
  metrics jsonb not null default '{}'::jsonb,
  evidence jsonb not null default '[]'::jsonb,
  source_run_id text,
  reviewed_by uuid references auth.users(id),
  reviewed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.homepilot_interactions (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.homepilot_tenants(id) on delete cascade,
  property_id text not null references public.homepilot_properties(id) on delete cascade,
  campaign_id uuid references public.homepilot_campaigns(id) on delete set null,
  module_key text not null references public.homepilot_modules(key),
  interaction_type text not null check (interaction_type in (
    'flyer_sent','direct_mail','email','email_sent','landing_page_scan','scan','click','form_submit','call','meeting','note','status_change','exported'
  )),
  sentiment text check (sentiment in ('positive','neutral','negative','unknown')),
  response_status text check (response_status in (
    'none','clicked','interested','not_interested','later','appointment','customer','no_response','wrong_address','do_not_contact'
  )),
  objection_code text,
  detail text,
  metadata jsonb not null default '{}'::jsonb,
  occurred_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

create table if not exists public.homepilot_response_insights (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.homepilot_tenants(id) on delete cascade,
  campaign_id uuid references public.homepilot_campaigns(id) on delete cascade,
  module_key text not null references public.homepilot_modules(key),
  insight_type text not null check (insight_type in ('objection','message_fit','segment_performance','timing','territory','recommendation')),
  title text not null,
  body text not null,
  supporting_metrics jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.homepilot_exports (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.homepilot_tenants(id) on delete cascade,
  module_key text references public.homepilot_modules(key),
  export_type text not null check (export_type in ('csv','xlsx','pdf','json','api')),
  filters jsonb not null default '{}'::jsonb,
  storage_path text,
  row_count integer,
  created_by uuid references auth.users(id),
  created_at timestamptz not null default now()
);

create table if not exists public.homepilot_audit_events (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.homepilot_tenants(id) on delete cascade,
  actor_user_id uuid references auth.users(id) on delete set null,
  module_key text references public.homepilot_modules(key),
  event_type text not null check (event_type in (
    'access_audit_failed','access_audit_passed','customer_package_generated',
    'dashboard_snapshot_generated','data_imported','delete_plan_generated',
    'export_generated','preflight_run','readiness_pack_generated',
    'retention_reviewed','rls_probe_run'
  )),
  subject_type text,
  subject_id text,
  severity text not null default 'info' check (severity in ('info','warn','fail','security')),
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.homepilot_platform_benchmarks (
  id uuid primary key default gen_random_uuid(),
  module_key text not null references public.homepilot_modules(key),
  benchmark_key text not null,
  cohort jsonb not null default '{}'::jsonb,
  sample_size integer not null check (sample_size >= 10),
  metrics jsonb not null default '{}'::jsonb,
  computed_at timestamptz not null default now(),
  unique (module_key, benchmark_key, cohort)
);

create table if not exists public.homepilot_source_runs (
  id text primary key default gen_random_uuid()::text,
  tenant_id uuid not null references public.homepilot_tenants(id) on delete cascade,
  module_key text references public.homepilot_modules(key),
  source_name text not null,
  publisher text,
  source_url text not null,
  licence text not null,
  allowed_use text not null,
  attribution text,
  retrieval_started_at timestamptz,
  retrieval_finished_at timestamptz,
  update_frequency text,
  transform_version text,
  operator text,
  status text not null default 'planned' check (status in ('planned','running','imported','failed','retired')),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.homepilot_geographies (
  id text primary key default gen_random_uuid()::text,
  tenant_id uuid not null references public.homepilot_tenants(id) on delete cascade,
  source_run_id text references public.homepilot_source_runs(id) on delete set null,
  geography_type text not null check (geography_type in ('address','statistical_sector','municipality','region','parcel','building','zone','custom')),
  geography_key text not null,
  country_code text not null default 'BE',
  region text,
  municipality text,
  postcode text,
  geometry_ref text,
  centroid_lat double precision,
  centroid_lon double precision,
  licence text,
  attribution text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (tenant_id, geography_type, geography_key)
);

create table if not exists public.homepilot_public_features (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.homepilot_tenants(id) on delete cascade,
  geography_id text not null references public.homepilot_geographies(id) on delete cascade,
  source_run_id text references public.homepilot_source_runs(id) on delete set null,
  feature_key text not null,
  feature_value jsonb not null default '{}'::jsonb,
  value_numeric numeric,
  value_text text,
  unit text,
  confidence numeric check (confidence is null or (confidence >= 0 and confidence <= 1)),
  observed_at timestamptz,
  licence text,
  attribution text,
  allowed_use text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (tenant_id, geography_id, feature_key, source_run_id)
);

create table if not exists public.homepilot_property_enrichments (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.homepilot_tenants(id) on delete cascade,
  property_id text not null references public.homepilot_properties(id) on delete cascade,
  source_run_id text references public.homepilot_source_runs(id) on delete set null,
  geography_id text references public.homepilot_geographies(id) on delete set null,
  enrichment_type text not null check (enrichment_type in ('official_address','parcel_geometry','building_geometry','statistical_context','land_use_environment','permit_planning','energy_context','osm_context','custom')),
  public_fields jsonb not null default '{}'::jsonb,
  confidence numeric check (confidence is null or (confidence >= 0 and confidence <= 1)),
  provenance jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, property_id, source_run_id, enrichment_type)
);

alter table public.homepilot_memberships add column if not exists partner_id text;
alter table public.homepilot_campaigns add column if not exists partner_id text;
alter table public.homepilot_campaigns add column if not exists partner_name text;
alter table public.homepilot_campaigns add column if not exists metadata jsonb not null default '{}'::jsonb;

create index if not exists idx_homepilot_memberships_partner on public.homepilot_memberships(tenant_id, partner_id) where partner_id is not null;
create index if not exists idx_homepilot_properties_tenant on public.homepilot_properties(tenant_id);
create index if not exists idx_homepilot_properties_geo on public.homepilot_properties(lat, lon);
create index if not exists idx_homepilot_properties_partner on public.homepilot_properties(tenant_id, ((core->'network'->>'partner_id')));
create index if not exists idx_homepilot_assessments_tenant_module on public.homepilot_assessments(tenant_id, module_key);
create index if not exists idx_homepilot_assessments_property on public.homepilot_assessments(property_id);
create index if not exists idx_homepilot_campaigns_partner on public.homepilot_campaigns(tenant_id, module_key, partner_id);
create index if not exists idx_homepilot_campaign_targets_campaign on public.homepilot_campaign_targets(campaign_id);
create index if not exists idx_homepilot_campaign_targets_partner on public.homepilot_campaign_targets(tenant_id, module_key, ((metadata->>'partner_id')));
create index if not exists idx_homepilot_interactions_property on public.homepilot_interactions(property_id, occurred_at desc);
create index if not exists idx_homepilot_interactions_campaign on public.homepilot_interactions(campaign_id, occurred_at desc);
create index if not exists idx_homepilot_interactions_partner on public.homepilot_interactions(tenant_id, module_key, ((metadata->>'partner_id')));
create index if not exists idx_homepilot_audit_events_tenant_time on public.homepilot_audit_events(tenant_id, created_at desc);
create index if not exists idx_homepilot_audit_events_type on public.homepilot_audit_events(event_type, created_at desc);
create index if not exists idx_homepilot_source_runs_tenant_source on public.homepilot_source_runs(tenant_id, source_name, created_at desc);
create index if not exists idx_homepilot_source_runs_module on public.homepilot_source_runs(tenant_id, module_key) where module_key is not null;
create index if not exists idx_homepilot_geographies_tenant_type on public.homepilot_geographies(tenant_id, geography_type, geography_key);
create index if not exists idx_homepilot_public_features_geography on public.homepilot_public_features(tenant_id, geography_id, feature_key);
create index if not exists idx_homepilot_public_features_source on public.homepilot_public_features(tenant_id, source_run_id);
create index if not exists idx_homepilot_property_enrichments_property on public.homepilot_property_enrichments(tenant_id, property_id);
create index if not exists idx_homepilot_property_enrichments_source on public.homepilot_property_enrichments(tenant_id, source_run_id);

create or replace function public.homepilot_membership_role(target_tenant uuid)
returns text
language sql
security definer
set search_path = public
as $$
  select m.role
  from public.homepilot_memberships m
  where m.tenant_id = target_tenant
    and m.user_id = auth.uid()
  limit 1
$$;


create or replace function public.homepilot_membership_partner_id(target_tenant uuid)
returns text
language sql
security definer
set search_path = public
as $$
  select nullif(m.partner_id, '')
  from public.homepilot_memberships m
  where m.tenant_id = target_tenant
    and m.user_id = auth.uid()
  limit 1
$$;

create or replace function public.homepilot_partner_scope_matches(target_tenant uuid, row_partner_id text)
returns boolean
language sql
security definer
set search_path = public
as $$
  select public.homepilot_has_tenant_access(target_tenant)
    and (
      public.homepilot_membership_partner_id(target_tenant) is null
      or nullif(row_partner_id, '') = public.homepilot_membership_partner_id(target_tenant)
    )
$$;

create or replace function public.homepilot_property_partner_id(target_property_id text)
returns text
language sql
security definer
set search_path = public
as $$
  select coalesce(p.core->'network'->>'partner_id', p.core->>'partner_id')
  from public.homepilot_properties p
  where p.id = target_property_id
  limit 1
$$;

create or replace function public.homepilot_campaign_partner_id(target_campaign_id uuid)
returns text
language sql
security definer
set search_path = public
as $$
  select coalesce(c.partner_id, c.metadata->>'partner_id', c.territory->>'partner_id', c.territory->'network'->>'partner_id')
  from public.homepilot_campaigns c
  where c.id = target_campaign_id
  limit 1
$$;

create or replace function public.homepilot_has_tenant_access(target_tenant uuid)
returns boolean
language sql
security definer
set search_path = public
as $$
  select public.homepilot_membership_role(target_tenant) is not null
$$;

create or replace function public.homepilot_can_write_tenant(target_tenant uuid)
returns boolean
language sql
security definer
set search_path = public
as $$
  select coalesce(public.homepilot_membership_role(target_tenant), '') in ('manager','admin','owner')
$$;

create or replace function public.homepilot_has_module_access(target_tenant uuid, target_module text)
returns boolean
language sql
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.homepilot_tenant_modules tm
    where tm.tenant_id = target_tenant
      and tm.module_key = target_module
      and tm.enabled is true
  )
  and public.homepilot_has_tenant_access(target_tenant)
$$;

alter table public.homepilot_tenants enable row level security;
alter table public.homepilot_memberships enable row level security;
alter table public.homepilot_modules enable row level security;
alter table public.homepilot_tenant_modules enable row level security;
alter table public.homepilot_properties enable row level security;
alter table public.homepilot_property_media enable row level security;
alter table public.homepilot_campaigns enable row level security;
alter table public.homepilot_campaign_targets enable row level security;
alter table public.homepilot_assessments enable row level security;
alter table public.homepilot_interactions enable row level security;
alter table public.homepilot_response_insights enable row level security;
alter table public.homepilot_exports enable row level security;
alter table public.homepilot_audit_events enable row level security;
alter table public.homepilot_platform_benchmarks enable row level security;
alter table public.homepilot_source_runs enable row level security;
alter table public.homepilot_geographies enable row level security;
alter table public.homepilot_public_features enable row level security;
alter table public.homepilot_property_enrichments enable row level security;

drop policy if exists "homepilot tenants read own" on public.homepilot_tenants;
drop policy if exists "homepilot memberships read own" on public.homepilot_memberships;
drop policy if exists "homepilot modules read" on public.homepilot_modules;
drop policy if exists "homepilot tenant modules read own" on public.homepilot_tenant_modules;
drop policy if exists "homepilot properties read own" on public.homepilot_properties;
drop policy if exists "homepilot properties write own" on public.homepilot_properties;
drop policy if exists "homepilot media read own module" on public.homepilot_property_media;
drop policy if exists "homepilot campaigns read own module" on public.homepilot_campaigns;
drop policy if exists "homepilot campaign targets read own module" on public.homepilot_campaign_targets;
drop policy if exists "homepilot assessments read own module" on public.homepilot_assessments;
drop policy if exists "homepilot interactions read own module" on public.homepilot_interactions;
drop policy if exists "homepilot response insights read own module" on public.homepilot_response_insights;
drop policy if exists "homepilot exports read own" on public.homepilot_exports;
drop policy if exists "homepilot audit events read own" on public.homepilot_audit_events;
drop policy if exists "homepilot audit events insert managers" on public.homepilot_audit_events;
drop policy if exists "homepilot source runs read own" on public.homepilot_source_runs;
drop policy if exists "homepilot source runs write managers" on public.homepilot_source_runs;
drop policy if exists "homepilot geographies read own" on public.homepilot_geographies;
drop policy if exists "homepilot geographies write managers" on public.homepilot_geographies;
drop policy if exists "homepilot public features read own" on public.homepilot_public_features;
drop policy if exists "homepilot public features write managers" on public.homepilot_public_features;
drop policy if exists "homepilot property enrichments read own" on public.homepilot_property_enrichments;
drop policy if exists "homepilot property enrichments write managers" on public.homepilot_property_enrichments;

create policy "homepilot tenants read own"
on public.homepilot_tenants for select
to authenticated
using (public.homepilot_has_tenant_access(id));

create policy "homepilot memberships read own"
on public.homepilot_memberships for select
to authenticated
using (
  user_id = auth.uid()
  or (
    public.homepilot_has_tenant_access(tenant_id)
    and public.homepilot_membership_partner_id(tenant_id) is null
  )
);

create policy "homepilot modules read"
on public.homepilot_modules for select
to authenticated
using (true);

create policy "homepilot tenant modules read own"
on public.homepilot_tenant_modules for select
to authenticated
using (public.homepilot_has_tenant_access(tenant_id));

create policy "homepilot properties read own"
on public.homepilot_properties for select
to authenticated
using (
  public.homepilot_has_tenant_access(tenant_id)
  and public.homepilot_partner_scope_matches(tenant_id, coalesce(core->'network'->>'partner_id', core->>'partner_id'))
);

create policy "homepilot properties write own"
on public.homepilot_properties for all
to authenticated
using (
  public.homepilot_can_write_tenant(tenant_id)
  and public.homepilot_partner_scope_matches(tenant_id, coalesce(core->'network'->>'partner_id', core->>'partner_id'))
)
with check (
  public.homepilot_can_write_tenant(tenant_id)
  and public.homepilot_partner_scope_matches(tenant_id, coalesce(core->'network'->>'partner_id', core->>'partner_id'))
);

create policy "homepilot media read own module"
on public.homepilot_property_media for select
to authenticated
using (
  public.homepilot_has_tenant_access(tenant_id)
  and (module_key is null or public.homepilot_has_module_access(tenant_id, module_key))
  and public.homepilot_partner_scope_matches(tenant_id, public.homepilot_property_partner_id(property_id))
);

create policy "homepilot campaigns read own module"
on public.homepilot_campaigns for select
to authenticated
using (
  public.homepilot_has_tenant_access(tenant_id)
  and public.homepilot_has_module_access(tenant_id, module_key)
  and public.homepilot_partner_scope_matches(
    tenant_id,
    coalesce(partner_id, metadata->>'partner_id', territory->>'partner_id', territory->'network'->>'partner_id')
  )
);

create policy "homepilot campaign targets read own module"
on public.homepilot_campaign_targets for select
to authenticated
using (
  public.homepilot_has_tenant_access(tenant_id)
  and public.homepilot_has_module_access(tenant_id, module_key)
  and public.homepilot_partner_scope_matches(
    tenant_id,
    coalesce(metadata->>'partner_id', public.homepilot_campaign_partner_id(campaign_id), public.homepilot_property_partner_id(property_id))
  )
);

create policy "homepilot assessments read own module"
on public.homepilot_assessments for select
to authenticated
using (
  public.homepilot_has_tenant_access(tenant_id)
  and public.homepilot_has_module_access(tenant_id, module_key)
  and public.homepilot_partner_scope_matches(tenant_id, public.homepilot_property_partner_id(property_id))
);

create policy "homepilot interactions read own module"
on public.homepilot_interactions for select
to authenticated
using (
  public.homepilot_has_tenant_access(tenant_id)
  and public.homepilot_has_module_access(tenant_id, module_key)
  and public.homepilot_partner_scope_matches(
    tenant_id,
    coalesce(metadata->>'partner_id', public.homepilot_campaign_partner_id(campaign_id), public.homepilot_property_partner_id(property_id))
  )
);

create policy "homepilot response insights read own module"
on public.homepilot_response_insights for select
to authenticated
using (
  public.homepilot_has_tenant_access(tenant_id)
  and public.homepilot_has_module_access(tenant_id, module_key)
  and public.homepilot_partner_scope_matches(
    tenant_id,
    coalesce(supporting_metrics->>'partner_id', public.homepilot_campaign_partner_id(campaign_id))
  )
);

create policy "homepilot exports read own"
on public.homepilot_exports for select
to authenticated
using (
  public.homepilot_has_tenant_access(tenant_id)
  and (module_key is null or public.homepilot_has_module_access(tenant_id, module_key))
  and public.homepilot_partner_scope_matches(tenant_id, filters->>'partner_id')
);

create policy "homepilot audit events read own"
on public.homepilot_audit_events for select
to authenticated
using (
  public.homepilot_has_tenant_access(tenant_id)
  and (module_key is null or public.homepilot_has_module_access(tenant_id, module_key))
  and public.homepilot_partner_scope_matches(tenant_id, details->>'partner_id')
);

create policy "homepilot audit events insert managers"
on public.homepilot_audit_events for insert
to authenticated
with check (
  public.homepilot_can_write_tenant(tenant_id)
  and (module_key is null or public.homepilot_has_module_access(tenant_id, module_key))
  and public.homepilot_partner_scope_matches(tenant_id, details->>'partner_id')
);

create policy "homepilot source runs read own"
on public.homepilot_source_runs for select
to authenticated
using (
  public.homepilot_has_tenant_access(tenant_id)
  and (module_key is null or public.homepilot_has_module_access(tenant_id, module_key))
);

create policy "homepilot source runs write managers"
on public.homepilot_source_runs for all
to authenticated
using (
  public.homepilot_can_write_tenant(tenant_id)
  and (module_key is null or public.homepilot_has_module_access(tenant_id, module_key))
)
with check (
  public.homepilot_can_write_tenant(tenant_id)
  and (module_key is null or public.homepilot_has_module_access(tenant_id, module_key))
);

create policy "homepilot geographies read own"
on public.homepilot_geographies for select
to authenticated
using (public.homepilot_has_tenant_access(tenant_id));

create policy "homepilot geographies write managers"
on public.homepilot_geographies for all
to authenticated
using (public.homepilot_can_write_tenant(tenant_id))
with check (public.homepilot_can_write_tenant(tenant_id));

create policy "homepilot public features read own"
on public.homepilot_public_features for select
to authenticated
using (public.homepilot_has_tenant_access(tenant_id));

create policy "homepilot public features write managers"
on public.homepilot_public_features for all
to authenticated
using (public.homepilot_can_write_tenant(tenant_id))
with check (public.homepilot_can_write_tenant(tenant_id));

create policy "homepilot property enrichments read own"
on public.homepilot_property_enrichments for select
to authenticated
using (
  public.homepilot_has_tenant_access(tenant_id)
  and public.homepilot_partner_scope_matches(tenant_id, public.homepilot_property_partner_id(property_id))
);

create policy "homepilot property enrichments write managers"
on public.homepilot_property_enrichments for all
to authenticated
using (
  public.homepilot_can_write_tenant(tenant_id)
  and public.homepilot_partner_scope_matches(tenant_id, public.homepilot_property_partner_id(property_id))
)
with check (
  public.homepilot_can_write_tenant(tenant_id)
  and public.homepilot_partner_scope_matches(tenant_id, public.homepilot_property_partner_id(property_id))
);

-- No read policy for platform benchmarks yet. Expose only through curated,
-- aggregate benchmark views once privacy thresholds are implemented.
