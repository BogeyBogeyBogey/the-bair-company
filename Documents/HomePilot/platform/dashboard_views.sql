-- HomePilot dashboard and export read models.
-- Apply after supabase_schema.sql.
--
-- These views are security invoker views so Supabase RLS on the underlying
-- homepilot_* tables remains the source of truth for tenant, module, and partner access.

create or replace function public.homepilot_metrics_for_customer(target_module text, raw_metrics jsonb)
returns jsonb
language sql
stable
security invoker
as $$
  select coalesce(jsonb_object_agg(metric.key, metric.value), '{}'::jsonb)
  from jsonb_each(coalesce(raw_metrics, '{}'::jsonb)) as metric(key, value)
  left join public.homepilot_modules module_def
    on module_def.key = target_module
  left join lateral (
    select item->>'visibility' as visibility
    from jsonb_array_elements(coalesce(module_def.metric_catalog, '[]'::jsonb)) item
    where item->>'key' = metric.key
    limit 1
  ) catalog on true
  where coalesce(
    catalog.visibility,
    case
      when metric.key in ('estimated_value', 'pipeline_value', 'project_value', 'deal_value') then 'tenant_private'
      else 'internal'
    end
  ) in ('benchmarkable', 'tenant_private')
$$;

create or replace view public.homepilot_property_intelligence
with (security_invoker = true)
as
select
  p.tenant_id,
  p.id as property_id,
  p.source_external_id,
  p.address,
  p.postcode,
  p.city,
  p.country_code,
  p.lat,
  p.lon,
  p.property_type,
  p.tags,
  p.core,
  coalesce(p.core->'network'->>'partner_id', p.core->>'partner_id', ct.metadata->>'partner_id') as partner_id,
  coalesce(p.core->'network'->>'partner_name', p.core->>'partner_name', ct.metadata->>'partner_name') as partner_name,
  a.id as assessment_id,
  a.module_key,
  m.label as module_label,
  m.category as module_category,
  a.score,
  a.grade,
  a.confidence,
  public.homepilot_metrics_for_customer(a.module_key, a.metrics) as metrics,
  a.evidence,
  case
    when jsonb_typeof(a.evidence) = 'array' then jsonb_array_length(a.evidence)
    else 0
  end as evidence_count,
  ct.campaign_id,
  ct.status as campaign_status,
  ct.priority_score,
  ct.priority_grade,
  ct.next_action_at,
  ct.last_interaction_at,
  latest_interaction.occurred_at as latest_interaction_at,
  latest_interaction.interaction_type as latest_interaction_type,
  latest_interaction.response_status as latest_response_status,
  latest_interaction.sentiment as latest_sentiment,
  latest_interaction.objection_code as latest_objection_code,
  latest_interaction.detail as latest_interaction_detail,
  coalesce(interaction_counts.interaction_count, 0) as interaction_count,
  p.created_at,
  p.updated_at
from public.homepilot_properties p
join public.homepilot_assessments a
  on a.tenant_id = p.tenant_id
  and a.property_id = p.id
join public.homepilot_modules m
  on m.key = a.module_key
left join lateral (
  select target.*
  from public.homepilot_campaign_targets target
  where target.tenant_id = p.tenant_id
    and target.property_id = p.id
    and target.module_key = a.module_key
  order by target.updated_at desc, target.created_at desc
  limit 1
) ct on true
left join lateral (
  select interaction.*
  from public.homepilot_interactions interaction
  where interaction.tenant_id = p.tenant_id
    and interaction.property_id = p.id
    and interaction.module_key = a.module_key
  order by interaction.occurred_at desc, interaction.created_at desc
  limit 1
) latest_interaction on true
left join lateral (
  select count(*)::integer as interaction_count
  from public.homepilot_interactions interaction
  where interaction.tenant_id = p.tenant_id
    and interaction.property_id = p.id
    and interaction.module_key = a.module_key
) interaction_counts on true
where public.homepilot_has_tenant_access(p.tenant_id)
  and public.homepilot_has_module_access(p.tenant_id, a.module_key)
  and public.homepilot_partner_scope_matches(
    p.tenant_id,
    coalesce(p.core->'network'->>'partner_id', p.core->>'partner_id', ct.metadata->>'partner_id')
  );

create or replace view public.homepilot_property_export
with (security_invoker = true)
as
select
  tenant_id,
  property_id,
  source_external_id,
  address,
  postcode,
  city,
  country_code,
  lat,
  lon,
  property_type,
  partner_id,
  partner_name,
  module_key,
  module_label,
  score,
  grade,
  confidence,
  campaign_id,
  campaign_status,
  priority_score,
  priority_grade,
  next_action_at,
  last_interaction_at,
  latest_interaction_at,
  latest_interaction_type,
  latest_response_status,
  latest_sentiment,
  latest_objection_code,
  latest_interaction_detail,
  interaction_count,
  evidence_count,
  tags,
  metrics,
  core,
  created_at,
  updated_at
from public.homepilot_property_intelligence;

create or replace view public.homepilot_property_public_enrichment
with (security_invoker = true)
as
select
  e.tenant_id,
  e.property_id,
  p.address,
  p.postcode,
  p.city,
  coalesce(p.core->'network'->>'partner_id', p.core->>'partner_id') as partner_id,
  coalesce(p.core->'network'->>'partner_name', p.core->>'partner_name') as partner_name,
  e.enrichment_type,
  e.public_fields,
  e.confidence,
  e.provenance,
  g.geography_type,
  g.geography_key,
  g.country_code,
  g.region,
  g.municipality,
  g.geometry_ref,
  s.id as source_run_id,
  s.source_name,
  s.publisher,
  s.source_url,
  s.licence,
  s.allowed_use,
  s.attribution,
  s.retrieval_finished_at,
  s.transform_version,
  e.created_at,
  e.updated_at
from public.homepilot_property_enrichments e
join public.homepilot_properties p
  on p.tenant_id = e.tenant_id
  and p.id = e.property_id
left join public.homepilot_geographies g
  on g.tenant_id = e.tenant_id
  and g.id = e.geography_id
left join public.homepilot_source_runs s
  on s.tenant_id = e.tenant_id
  and s.id = e.source_run_id
where public.homepilot_has_tenant_access(e.tenant_id)
  and public.homepilot_partner_scope_matches(
    e.tenant_id,
    coalesce(p.core->'network'->>'partner_id', p.core->>'partner_id')
  );

create or replace view public.homepilot_campaign_metrics
with (security_invoker = true)
as
select
  c.tenant_id,
  c.id as campaign_id,
  c.module_key,
  c.name as campaign_name,
  c.channel,
  c.status as campaign_lifecycle_status,
  c.territory,
  c.message_variant,
  c.partner_id,
  c.partner_name,
  c.metadata,
  count(ct.id)::integer as target_count,
  count(*) filter (where ct.status in ('sent','scanned','clicked','responded','appointment','customer','no_response'))::integer as contacted_count,
  count(*) filter (where ct.status in ('responded','appointment','customer'))::integer as response_count,
  count(*) filter (where ct.status in ('appointment','customer'))::integer as appointment_count,
  count(*) filter (where ct.status = 'no_response')::integer as no_response_count,
  round(avg(ct.priority_score), 2) as average_priority_score,
  case
    when count(*) filter (where ct.status in ('sent','scanned','clicked','responded','appointment','customer','no_response')) = 0 then 0
    else round(
      (
        count(*) filter (where ct.status in ('responded','appointment','customer'))::numeric
        / count(*) filter (where ct.status in ('sent','scanned','clicked','responded','appointment','customer','no_response'))::numeric
      ) * 100,
      2
    )
  end as response_rate_pct,
  case
    when count(ct.id) = 0 then 0
    else round(
      (count(*) filter (where ct.status in ('responded','appointment','customer'))::numeric / count(ct.id)::numeric) * 100,
      2
    )
  end as target_response_rate_pct,
  min(c.started_at) as started_at,
  max(c.ended_at) as ended_at,
  max(ct.updated_at) as last_target_update_at
from public.homepilot_campaigns c
left join public.homepilot_campaign_targets ct
  on ct.tenant_id = c.tenant_id
  and ct.campaign_id = c.id
  and ct.module_key = c.module_key
where public.homepilot_has_tenant_access(c.tenant_id)
  and public.homepilot_has_module_access(c.tenant_id, c.module_key)
  and public.homepilot_partner_scope_matches(
    c.tenant_id,
    coalesce(c.partner_id, c.metadata->>'partner_id', c.territory->>'partner_id', c.territory->'network'->>'partner_id')
  )
group by
  c.tenant_id,
  c.id,
  c.module_key,
  c.name,
  c.channel,
  c.status,
  c.territory,
  c.message_variant,
  c.partner_id,
  c.partner_name,
  c.metadata;

create or replace view public.homepilot_module_metrics
with (security_invoker = true)
as
select
  a.tenant_id,
  a.module_key,
  m.label as module_label,
  m.category as module_category,
  count(distinct a.property_id)::integer as property_count,
  round(avg(a.score), 2) as average_score,
  count(*) filter (where a.grade in ('A+', 'A'))::integer as top_opportunity_count,
  count(*) filter (where ct.status in ('sent','scanned','clicked','responded','appointment','customer','no_response'))::integer as contacted_count,
  count(*) filter (where ct.status in ('responded','appointment','customer'))::integer as response_count,
  count(*) filter (where ct.status in ('appointment','customer'))::integer as appointment_count,
  case
    when count(*) filter (where ct.status in ('sent','scanned','clicked','responded','appointment','customer','no_response')) = 0 then 0
    else round(
      (
        count(*) filter (where ct.status in ('responded','appointment','customer'))::numeric
        / count(*) filter (where ct.status in ('sent','scanned','clicked','responded','appointment','customer','no_response'))::numeric
      ) * 100,
      2
    )
  end as response_rate_pct,
  case
    when count(ct.id) = 0 then 0
    else round(
      (count(*) filter (where ct.status in ('responded','appointment','customer'))::numeric / count(ct.id)::numeric) * 100,
      2
    )
  end as target_response_rate_pct,
  max(a.updated_at) as last_assessment_at
from public.homepilot_assessments a
join public.homepilot_modules m
  on m.key = a.module_key
left join public.homepilot_campaign_targets ct
  on ct.tenant_id = a.tenant_id
  and ct.property_id = a.property_id
  and ct.module_key = a.module_key
where public.homepilot_has_tenant_access(a.tenant_id)
  and public.homepilot_has_module_access(a.tenant_id, a.module_key)
group by
  a.tenant_id,
  a.module_key,
  m.label,
  m.category;

create or replace view public.homepilot_second_brain_edges
with (security_invoker = true)
as
select
  tenant_id,
  module_key,
  'module'::text as source_type,
  module_key as source_id,
  'property'::text as target_type,
  property_id as target_id,
  'scores'::text as edge_type,
  coalesce(score, 0)::numeric as weight
from public.homepilot_property_intelligence
union all
select
  tenant_id,
  module_key,
  'campaign'::text as source_type,
  campaign_id::text as source_id,
  'property'::text as target_type,
  property_id as target_id,
  'contacts'::text as edge_type,
  coalesce(priority_score, score, 0)::numeric as weight
from public.homepilot_property_intelligence
where campaign_id is not null
union all
select
  tenant_id,
  module_key,
  'property'::text as source_type,
  property_id as source_id,
  'reaction'::text as target_type,
  coalesce(latest_response_status, latest_interaction_type, 'none') as target_id,
  'produces'::text as edge_type,
  greatest(coalesce(score, 0)::numeric, 1) as weight
from public.homepilot_property_intelligence
where latest_interaction_at is not null;

grant select on public.homepilot_property_intelligence to authenticated;
grant select on public.homepilot_property_export to authenticated;
grant select on public.homepilot_campaign_metrics to authenticated;
grant select on public.homepilot_module_metrics to authenticated;
grant select on public.homepilot_second_brain_edges to authenticated;
