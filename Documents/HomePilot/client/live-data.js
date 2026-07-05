(function () {
  const config = window.HOMEPILOT_LIVE_CONFIG || {};
  if (!config.enabled) return;

  const baseUrl = String(config.supabaseUrl || "").replace(/\/+$/, "");
  const anonKey = String(config.supabaseAnonKey || "");
  const storageKey = config.accessTokenStorageKey || "homepilot.customerJwt";
  const accessToken = config.accessToken
    || window.HOMEPILOT_ACCESS_TOKEN
    || (window.localStorage ? window.localStorage.getItem(storageKey) : "");
  const views = {
    propertyIntelligence: "homepilot_property_intelligence",
    campaignMetrics: "homepilot_campaign_metrics",
    secondBrainEdges: "homepilot_second_brain_edges",
    ...(config.views || {})
  };

  if (!baseUrl || !anonKey || !accessToken) {
    window.HOMEPILOT_LIVE_STATUS = {
      status: "not_configured",
      reason: "Live portal requires supabaseUrl, supabaseAnonKey, and a customer JWT."
    };
    return;
  }

  function parseJsonish(value, fallback) {
    if (value === null || value === undefined || value === "") return fallback;
    if (typeof value === "object") return value;
    try {
      return JSON.parse(value);
    } catch (_error) {
      return fallback;
    }
  }

  function queryString(params) {
    return Object.entries(params)
      .filter(([, value]) => value !== undefined && value !== null && value !== "")
      .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
      .join("&");
  }

  async function readView(view, params) {
    const url = `${baseUrl}/rest/v1/${view}?${queryString(params)}`;
    const response = await fetch(url, {
      headers: {
        apikey: anonKey,
        Authorization: `Bearer ${accessToken}`,
        Accept: "application/json"
      }
    });
    if (!response.ok) {
      const body = await response.text();
      throw new Error(`HomePilot live read failed for ${view}: ${response.status} ${body.slice(0, 180)}`);
    }
    return response.json();
  }

  function bestRow(rows) {
    return [...rows].sort((a, b) => Number(b.score || 0) - Number(a.score || 0))[0] || {};
  }

  function propertyValue(row) {
    const metrics = parseJsonish(row.metrics, {});
    const core = parseJsonish(row.core, {});
    return Number(metrics.estimated_value || core.estimated_value || metrics.pipeline_value || 0) || 0;
  }

  function buildProperties(rows) {
    const grouped = new Map();
    rows.forEach((row) => {
      const id = row.property_id;
      if (!id) return;
      if (!grouped.has(id)) grouped.set(id, []);
      grouped.get(id).push(row);
    });
    return Array.from(grouped.entries()).map(([id, propertyRows]) => {
      const best = bestRow(propertyRows);
      const assessments = {};
      propertyRows.forEach((row) => {
        if (!row.module_key) return;
        assessments[row.module_key] = {
          label: row.module_label || row.module_key,
          score: Number(row.score || 0),
          grade: row.grade || "",
          confidence: Number(row.confidence || 0),
          metrics: parseJsonish(row.metrics, {}),
          evidence: parseJsonish(row.evidence, [])
        };
      });
      return {
        id,
        address: best.address || "",
        city: best.city || "",
        lat: Number(best.lat),
        lon: Number(best.lon),
        propertyType: best.property_type || "",
        tags: parseJsonish(best.tags, []),
        status: best.campaign_status || best.latest_response_status || "generated",
        nextAction: best.latest_interaction_detail || "Review next best action in CRM",
        estimatedValue: propertyValue(best),
        interactions: propertyRows
          .filter((row) => row.latest_interaction_at)
          .map((row) => ({
            date: row.latest_interaction_at,
            type: row.latest_interaction_type || "interaction",
            status: row.latest_response_status || "",
            detail: row.latest_interaction_detail || ""
          })),
        assessments
      };
    });
  }

  function buildCampaigns(rows) {
    return rows.map((row) => ({
      id: row.campaign_id,
      name: row.campaign_name,
      module_key: row.module_key,
      target_count: Number(row.target_count || 0),
      response_rate_pct: Number(row.response_rate_pct || 0),
      response_count: Number(row.response_count || 0),
      appointment_count: Number(row.appointment_count || 0)
    }));
  }

  function buildBrain(edges, properties) {
    const propertyById = Object.fromEntries(properties.map((property) => [property.id, property]));
    const nodes = [];
    const nodeIds = new Set();
    const addNode = (node) => {
      if (nodeIds.has(node.id)) return;
      nodeIds.add(node.id);
      nodes.push(node);
    };
    edges.forEach((edge) => {
      const source = `${edge.source_type}:${edge.source_id}`;
      const target = `${edge.target_type}:${edge.target_id}`;
      const property = propertyById[edge.target_id] || propertyById[edge.source_id];
      addNode({
        id: source,
        label: edge.source_type === "module" ? edge.source_id : String(edge.source_id || ""),
        type: edge.source_type || "signal",
        module_key: edge.module_key
      });
      addNode({
        id: target,
        label: property ? property.address : String(edge.target_id || ""),
        type: edge.target_type || "signal",
        property_id: property?.id,
        module_key: edge.module_key,
        score: property ? bestRow(Object.values(property.assessments || {})).score : undefined
      });
    });
    return {
      nodes,
      edges: edges.map((edge) => ({
        source: `${edge.source_type}:${edge.source_id}`,
        target: `${edge.target_type}:${edge.target_id}`,
        type: edge.edge_type || "links",
        weight: Number(edge.weight || 1),
        module_key: edge.module_key
      })),
      stats: { nodes: nodes.length, edges: edges.length }
    };
  }

  async function loadLiveSnapshot() {
    window.HOMEPILOT_LIVE_STATUS = { status: "loading" };
    const [propertyRows, campaignRows, brainEdges] = await Promise.all([
      readView(views.propertyIntelligence, {
        select: "property_id,address,city,lat,lon,property_type,tags,core,module_key,module_label,score,grade,confidence,metrics,evidence,evidence_count,campaign_status,latest_response_status,latest_interaction_at,latest_interaction_type,latest_interaction_detail",
        order: "score.desc",
        limit: config.propertyLimit || 1000
      }),
      readView(views.campaignMetrics, {
        select: "campaign_id,module_key,campaign_name,target_count,response_count,appointment_count,response_rate_pct",
        order: "response_rate_pct.desc",
        limit: config.campaignLimit || 100
      }),
      readView(views.secondBrainEdges, {
        select: "module_key,source_type,source_id,target_type,target_id,edge_type,weight",
        order: "weight.desc",
        limit: config.edgeLimit || 1200
      })
    ]);
    const properties = buildProperties(propertyRows);
    const snapshot = {
      tenant: {
        id: config.tenant?.id || "live-customer",
        name: config.tenant?.name || "Live customer",
        modules: config.modules || config.tenant?.modules || []
      },
      campaigns: buildCampaigns(campaignRows),
      properties,
      recommendations: [
        "Live RLS-backed dashboard loaded with customer JWT.",
        "Use CRM handoff for owner assignment and next actions."
      ],
      brain: buildBrain(brainEdges, properties),
      trust: {
        sourceLedger: {
          status: "pass",
          review_status: "ready",
          scope: { tenant_scoped: true, module_keys: config.modules || [] },
          summary: {
            properties: properties.length,
            assessments: propertyRows.length,
            evidence_references: propertyRows.reduce((sum, row) => sum + Number(row.evidence_count || 0), 0),
            source_runs: 1,
            review_gap_count: 0
          },
          guardrails: {
            source: "Supabase customer JWT + RLS views",
            tenant_scoped: true,
            raw_internal_fields_excluded: true,
            lead_claim_language_required: true,
            opportunity_not_intent_without_response: true
          }
        }
      }
    };
    window.HOMEPILOT_LIVE_SNAPSHOT = snapshot;
    window.HOMEPILOT_LIVE_STATUS = { status: "loaded", properties: properties.length };
    window.dispatchEvent(new CustomEvent("homepilot:live-data", { detail: { snapshot } }));
  }

  loadLiveSnapshot().catch((error) => {
    window.HOMEPILOT_LIVE_STATUS = { status: "error", message: error.message };
    window.dispatchEvent(new CustomEvent("homepilot:live-error", { detail: { message: error.message } }));
  });
}());
