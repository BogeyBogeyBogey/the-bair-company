const EMPTY_DATA = {
  tenant: { id: "empty", name: "HomePilot", modules: [] },
  campaigns: [],
  properties: [],
  recommendations: []
};

let DATA = normalizeDashboardData(window.HOMEPILOT_LIVE_SNAPSHOT || window.HOMEPILOT_DASHBOARD || window.HOMEPILOT_SAMPLE || EMPTY_DATA);

function normalizeDashboardData(raw) {
  const data = raw && typeof raw === "object" ? raw : EMPTY_DATA;
  data.tenant = data.tenant || { id: "empty", name: "HomePilot", modules: [] };
  data.campaigns = Array.isArray(data.campaigns) ? data.campaigns : [];
  data.properties = Array.isArray(data.properties) ? data.properties : [];
  data.recommendations = Array.isArray(data.recommendations) ? data.recommendations : [];
  data.brain = data.brain && Array.isArray(data.brain.nodes) && Array.isArray(data.brain.edges)
    ? data.brain
    : { nodes: [], edges: [], stats: {} };
  data.visualIntelligence = data.visualIntelligence && typeof data.visualIntelligence === "object"
    ? data.visualIntelligence
    : { map: {}, graph: {} };
  data.leadPrioritization = data.leadPrioritization && typeof data.leadPrioritization === "object"
    ? data.leadPrioritization
    : {};
  data.partnerAssignment = data.partnerAssignment && typeof data.partnerAssignment === "object"
    ? data.partnerAssignment
    : {};
  data.campaignSegmentation = data.campaignSegmentation && typeof data.campaignSegmentation === "object"
    ? data.campaignSegmentation
    : {};
  data.messageStrategy = data.messageStrategy && typeof data.messageStrategy === "object"
    ? data.messageStrategy
    : {};
  data.openIntelligence = data.openIntelligence && typeof data.openIntelligence === "object"
    ? data.openIntelligence
    : {};
  data.trust = data.trust && typeof data.trust === "object" ? data.trust : {};
  data.network = data.network && typeof data.network === "object" ? data.network : null;
  data.accessLenses = Array.isArray(data.accessLenses) ? data.accessLenses : [];
  return data;
}

function discoverModules(data) {
  return Array.from(new Set([
    ...(data.tenant.modules || []),
    ...data.properties.flatMap((property) => Object.keys(property.assessments || {}))
  ]));
}

let discoveredModules = discoverModules(DATA);

const state = {
  selectedId: DATA.properties[0]?.id || "",
  view: "executive",
  search: "",
  grade: "all",
  status: "all",
  partnerId: "all",
  accessLens: "",
  modules: new Set(discoveredModules),
  brain: {
    scale: 1,
    tx: 0,
    ty: 0,
    pinned: {},
    selectedNodeId: "",
    moveMode: false,
    signature: ""
  }
};

const moduleLabels = {
  facadepilot: "Facade",
  windowpilot: "Windows",
  roofpilot: "Roof",
  gardenpilot: "Garden",
  poolpilot: "Pool",
  porchpilot: "Porch",
  drivewaypilot: "Driveway"
};

const CONTACTED_STATUSES = new Set(["sent", "scanned", "clicked", "responded", "appointment", "customer", "no_response"]);
const ENGAGED_STATUSES = new Set(["responded", "appointment", "customer"]);
const CONVERSION_STATUSES = new Set(["appointment", "customer"]);

function applyDashboardData(nextData) {
  DATA = normalizeDashboardData(nextData);
  discoveredModules = discoverModules(DATA);
  state.selectedId = DATA.properties[0]?.id || "";
  state.modules = new Set(discoveredModules);
  state.partnerId = "all";
  state.accessLens = "";
  state.brain.pinned = {};
  state.brain.selectedNodeId = "";
  state.brain.moveMode = false;
  state.brain.signature = "";
  state.brain.layout = null;
  renderTenantControls();
  renderModuleControls();
  renderPartnerControls();
  renderAccessLensControls();
  render();
}

window.HOMEPILOT_APPLY_DASHBOARD_DATA = applyDashboardData;
window.addEventListener("homepilot:live-data", (event) => {
  const snapshot = event.detail?.snapshot || event.detail;
  if (snapshot) applyDashboardData(snapshot);
});

function datasetIsSynthetic() {
  const tenantSettings = DATA.tenant?.settings || {};
  const hasSyntheticProperty = DATA.properties.some((property) => (
    property?.core?.demo ||
    property?.core?.synthetic_record ||
    property?.metadata?.demo ||
    property?.tags?.some?.((tag) => String(tag).toLowerCase().includes("synthetic"))
  ));
  return Boolean(tenantSettings.demo || tenantSettings.synthetic || hasSyntheticProperty);
}

function isDawWorkspace() {
  const values = [
    DATA.tenant?.id,
    DATA.tenant?.name,
    DATA.network?.producer?.id,
    DATA.network?.producer?.name,
    DATA.network?.product_focus
  ].map((value) => String(value || "").toLowerCase());
  return values.some((value) => value.includes("daw") || value.includes("crepi"));
}

function renderTenantControls() {
  const select = document.getElementById("tenantSelect");
  const badge = document.getElementById("demoBadge");
  const eyebrow = document.getElementById("workspaceEyebrow");
  const title = document.getElementById("workspaceTitle");
  const tenantId = DATA.tenant?.id || "homepilot-demo";
  const producerName = DATA.network?.producer?.name || "";
  const tenantName = producerName || DATA.tenant?.name || "HomePilot demo";
  const synthetic = datasetIsSynthetic();
  const daw = isDawWorkspace();
  const visibleName = daw ? "DAW Belgium (demo)" : `${tenantName}${synthetic && !String(tenantName).toLowerCase().includes("demo") ? " (demo)" : ""}`;

  if (select) {
    select.innerHTML = `<option value="${escapeHtml(tenantId)}">${escapeHtml(visibleName)}</option>`;
    select.value = tenantId;
  }
  if (badge) {
    badge.hidden = !synthetic;
    badge.textContent = synthetic ? "Demo · synthetic data" : "Live data";
  }
  if (eyebrow) {
    eyebrow.textContent = daw
      ? "DAW Belgium demo · synthetic buyer review"
      : synthetic ? "Synthetic buyer-review workspace" : "Live customer workspace";
  }
  if (title) {
    title.textContent = daw ? "Facade opportunity command center" : "Renovation opportunity command center";
  }
}

function renderModuleControls() {
  const stack = document.getElementById("moduleStack");
  if (!stack) return;
  stack.innerHTML = `
    <div class="sidebar-label">Modules</div>
    ${discoveredModules.map((key) => `
      <label><input type="checkbox" value="${key}" ${state.modules.has(key) ? "checked" : ""}> ${moduleLabels[key] || key}</label>
    `).join("")}
  `;
  stack.querySelectorAll("input").forEach((input) => {
    input.addEventListener("change", () => {
      if (input.checked) state.modules.add(input.value);
      else state.modules.delete(input.value);
      render();
    });
  });
}

function defaultAccessLenses() {
  const modules = discoveredModules.slice();
  const firstModule = modules.slice(0, 1);
  const partners = networkPartners();
  const producerName = DATA.network?.producer?.name || DATA.tenant?.name || "Producer network";
  const lenses = [
    {
      key: "producer_network",
      label: `${producerName} executive`,
      role: "owner",
      scope: partners.length ? "aggregate network plus partner drilldown" : "tenant-wide module workspace",
      partner_mode: "all",
      module_mode: "all",
      module_keys: modules,
      summary: "Aggregate view for the customer account.",
      blocked_visibility: ["other tenant raw addresses", "unapproved raw contact data"],
      live_gate: "blocked_until_live_rls_customer_access_proof",
      buyer_review_only: true
    },
    {
      key: "partner_renovator",
      label: "Partner renovator",
      role: "manager",
      scope: "assigned records only",
      partner_mode: "first_partner",
      partner_id: partners[0]?.id || "",
      module_mode: "all",
      module_keys: modules,
      summary: "Assigned-record cutdown for a renovation partner.",
      blocked_visibility: ["other partner raw addresses", "producer-wide raw exports"],
      live_gate: "blocked_until_live_rls_customer_access_and_partner_reconciliation",
      buyer_review_only: true
    },
    {
      key: "module_only_customer",
      label: "Module-only customer",
      role: "viewer",
      scope: "tenant plus entitled module rows only",
      partner_mode: "all",
      module_mode: "first_module",
      module_keys: firstModule,
      summary: "Single-pilot view for customers who bought one module.",
      blocked_visibility: ["disabled module metrics", "disabled module exports"],
      live_gate: "blocked_until_live_schema_rls_customer_access_proof",
      buyer_review_only: true
    }
  ];
  return partners.length ? lenses : lenses.filter((lens) => lens.key !== "partner_renovator");
}

function accessLenses() {
  const lenses = DATA.accessLenses.length ? DATA.accessLenses : defaultAccessLenses();
  return lenses.filter((lens) => lens && lens.key && lens.label);
}

function activeAccessLens() {
  const lenses = accessLenses();
  if (!lenses.length) return null;
  const current = lenses.find((lens) => lens.key === state.accessLens) || lenses[0];
  state.accessLens = current.key;
  return current;
}

function moduleSetForLens(lens) {
  const allModules = discoveredModules.slice();
  const lensModules = Array.isArray(lens?.module_keys)
    ? lens.module_keys.filter((key) => allModules.includes(key))
    : [];
  if (lens?.module_mode === "first_module") {
    return new Set((lensModules.length ? lensModules : allModules).slice(0, 1));
  }
  if (lensModules.length && lens?.module_mode !== "all") return new Set(lensModules);
  if (lensModules.length && lens?.module_keys_locked) return new Set(lensModules);
  return new Set(allModules);
}

function applyAccessLens(lensKey) {
  state.accessLens = lensKey;
  const lens = activeAccessLens();
  if (!lens) return;

  state.modules = moduleSetForLens(lens);
  const partners = networkPartners();
  if (lens.partner_mode === "first_partner") {
    const requested = lens.partner_id && partnerForId(lens.partner_id) ? lens.partner_id : partners[0]?.id;
    state.partnerId = requested || "all";
  } else if (lens.partner_mode === "selected_partner" && state.partnerId === "all" && partners[0]) {
    state.partnerId = partners[0].id;
  } else if (lens.partner_mode === "all") {
    state.partnerId = "all";
  }

  state.grade = "all";
  state.status = "all";
  const gradeFilter = document.getElementById("gradeFilter");
  const statusFilter = document.getElementById("statusFilter");
  if (gradeFilter) gradeFilter.value = "all";
  if (statusFilter) statusFilter.value = "all";
  state.brain.signature = "";
  renderModuleControls();
  renderPartnerControls();
  renderAccessLensControls();
}

function renderAccessLensControls() {
  const box = document.getElementById("accessLensBox");
  const select = document.getElementById("accessLensSelect");
  const note = document.getElementById("accessLensNote");
  if (!box || !select || !note) return;
  const lenses = accessLenses();
  if (!lenses.length) {
    box.hidden = true;
    return;
  }
  box.hidden = false;
  const lens = activeAccessLens();
  select.innerHTML = lenses.map((item) => `
    <option value="${escapeHtml(item.key)}">${escapeHtml(item.label)}</option>
  `).join("");
  select.value = lens?.key || lenses[0].key;
  note.textContent = lens?.scope || lens?.summary || "Buyer-review visibility lens";
}

function renderAccessLensPanel(properties) {
  const panel = document.getElementById("accessLensPanel");
  if (!panel) return;
  const lens = activeAccessLens();
  if (!lens) {
    panel.hidden = true;
    return;
  }
  panel.hidden = false;
  const status = document.getElementById("accessLensStatus");
  const partner = activePartner();
  const modules = Array.from(state.modules);
  const moduleNames = modules.map((key) => moduleLabels[key] || key);
  const blocked = Array.isArray(lens.blocked_visibility) ? lens.blocked_visibility : [];
  const partnerText = partner
    ? `${partner.name || partner.id} only`
    : networkPartners().length ? `${networkPartners().length} partners` : DATA.tenant?.name || "Tenant";
  if (status) {
    status.textContent = lens.live_access_ready ? "Live access ready" : "Buyer-review demo";
  }

  const cards = [
    {
      label: "Visible records",
      value: properties.length,
      detail: lens.scope || "scoped dashboard view",
      tone: "records"
    },
    {
      label: "Module scope",
      value: moduleNames.length || 0,
      detail: moduleNames.join(", ") || "No modules selected",
      tone: "modules"
    },
    {
      label: "Partner scope",
      value: partnerText,
      detail: partner ? "assigned-record cutdown" : "aggregate or tenant-wide view",
      tone: "partners"
    },
    {
      label: "Hidden by design",
      value: blocked.length,
      detail: blocked.slice(0, 2).join(" / ") || "raw cross-tenant data",
      tone: "blocked"
    },
    {
      label: "Live gate",
      value: lens.buyer_review_only ? "blocked" : "review",
      detail: humanizeKey(lens.live_gate || "buyer_review_only"),
      tone: "gate"
    }
  ];

  document.getElementById("accessLensCards").innerHTML = cards.map((card) => `
    <div class="access-lens-card ${escapeHtml(card.tone)}">
      <span>${escapeHtml(card.label)}</span>
      <strong>${escapeHtml(card.value)}</strong>
      <small>${escapeHtml(card.detail)}</small>
    </div>
  `).join("");
}

function networkPartners() {
  return Array.isArray(DATA.network?.partners) ? DATA.network.partners : [];
}

function partnerForId(partnerId) {
  return networkPartners().find((partner) => String(partner.id) === String(partnerId)) || null;
}

function propertyPartner(property) {
  return property?.partner && typeof property.partner === "object" ? property.partner : {};
}

function propertyPartnerId(property) {
  return String(propertyPartner(property).id || "");
}

function propertyPartnerName(property) {
  const partner = propertyPartner(property);
  return partner.name || property.partnerName || property.partner_name || "";
}

function activePartner() {
  return state.partnerId === "all" ? null : partnerForId(state.partnerId);
}

function networkScopeLabel() {
  const partner = activePartner();
  if (partner) return partner.name || partner.id;
  return DATA.network?.producer?.name || DATA.tenant?.name || "Network";
}

function estimatedFacadeM2(property) {
  const raw = property?.estimatedFacadeM2 ?? property?.estimated_facade_m2 ?? 0;
  const value = Number(raw);
  return Number.isFinite(value) ? value : 0;
}

function renderPartnerControls() {
  const box = document.getElementById("partnerLensBox");
  const select = document.getElementById("partnerSelect");
  const note = document.getElementById("partnerScopeNote");
  if (!box || !select || !note) return;
  const partners = networkPartners();
  if (!partners.length) {
    box.hidden = true;
    state.partnerId = "all";
    return;
  }
  const producerName = DATA.network?.producer?.name || "Producer network";
  box.hidden = false;
  if (state.partnerId !== "all" && !partnerForId(state.partnerId)) state.partnerId = "all";
  select.innerHTML = `
    <option value="all">${producerName} - all partners</option>
    ${partners.map((partner) => `<option value="${escapeHtml(partner.id)}">${escapeHtml(partner.name || partner.id)}</option>`).join("")}
  `;
  select.value = state.partnerId;
  const partner = activePartner();
  note.textContent = partner
    ? `${partner.region || partner.territory || "Partner"} records only`
    : `${producerName} aggregate plus partner drilldown`;
}

function bestAssessment(property) {
  return Object.entries(property.assessments || {})
    .filter(([key]) => state.modules.has(key))
    .map(([key, value]) => ({ key, ...value }))
    .sort((a, b) => b.score - a.score)[0];
}

function leadPriorityPlan() {
  return DATA.leadPrioritization || DATA.visualIntelligence?.leadPriority || {};
}

function leadPriorityRows() {
  const plan = leadPriorityPlan();
  return Array.isArray(plan.best_queue) ? plan.best_queue : [];
}

function openIntelligencePlan() {
  return DATA.openIntelligence || {};
}

function partnerAssignmentPlan() {
  return DATA.partnerAssignment || {};
}

function campaignSegmentationPlan() {
  return DATA.campaignSegmentation || {};
}

function messageStrategyPlan() {
  return DATA.messageStrategy || {};
}

function leadPriorityMap() {
  const map = new Map();
  leadPriorityRows().forEach((row) => {
    if (row && row.property_id) map.set(String(row.property_id), row);
  });
  return map;
}

function propertyPriorityScore(property, priorityMap = null) {
  const row = (priorityMap || leadPriorityMap()).get(String(property.id));
  if (row && Number.isFinite(Number(row.priority_score))) return Number(row.priority_score);
  return bestAssessment(property)?.score || 0;
}

function filteredProperties() {
  const query = state.search.trim().toLowerCase();
  return DATA.properties.filter((property) => {
    const best = bestAssessment(property);
    if (!best) return false;
    if (state.partnerId !== "all" && propertyPartnerId(property) !== state.partnerId) return false;
    if (state.grade !== "all" && best.grade !== state.grade) return false;
    if (state.status !== "all" && property.status !== state.status) return false;
    if (!query) return true;
    const haystack = [
      property.address,
      property.city,
      property.status,
      property.nextAction,
      propertyPartnerName(property),
      property.territory,
      property.producer,
      (property.tags || []).join(" "),
      Object.values(property.assessments || {}).map((item) => item.label).join(" ")
    ].join(" ").toLowerCase();
    return haystack.includes(query);
  });
}

function propertyValue(property) {
  const raw = property.estimatedValue ?? property.estimated_value ?? property.pipelineValue ?? property.pipeline_value ?? 0;
  const value = Number(raw);
  return Number.isFinite(value) ? value : 0;
}

function formatEuro(value) {
  return "EUR" + Math.round(Number(value) || 0).toLocaleString("en-US");
}

function formatPercent(value) {
  return Math.round(value) + "%";
}

function responseStatus(properties, status) {
  return properties.filter((property) => property.status === status).length;
}

function countByStatuses(properties, statuses) {
  return properties.filter((property) => statuses.has(property.status)).length;
}

function contactedCount(properties) {
  return countByStatuses(properties, CONTACTED_STATUSES);
}

function responseCount(properties) {
  return countByStatuses(properties, ENGAGED_STATUSES);
}

function conversionCount(properties) {
  return countByStatuses(properties, CONVERSION_STATUSES);
}

function contactedResponseRate(properties) {
  const contacted = contactedCount(properties);
  return contacted ? (responseCount(properties) / contacted) * 100 : 0;
}

function average(values) {
  const clean = values.filter((value) => Number.isFinite(Number(value)));
  if (!clean.length) return 0;
  return clean.reduce((sum, value) => sum + Number(value), 0) / clean.length;
}

function trustMetrics(properties) {
  const total = properties.length || 1;
  const geocoded = properties.filter((property) => Number.isFinite(Number(property.lat)) && Number.isFinite(Number(property.lon))).length;
  const withNextAction = properties.filter((property) => property.nextAction).length;
  const withInteractions = properties.filter((property) => (property.interactions || []).length > 0).length;
  const confidences = properties.flatMap((property) => Object.values(property.assessments || {}).map((item) => item.confidence * 100));
  const confidence = average(confidences);
  const score = Math.round(
    (geocoded / total) * 25
    + (withNextAction / total) * 25
    + (withInteractions / total) * 20
    + Math.min(30, confidence * 0.3)
  );
  return { total, geocoded, withNextAction, withInteractions, confidence, score };
}

function fallbackSourceLedger(properties) {
  const moduleCoverage = {};
  let assessments = 0;
  let evidenceRefs = 0;
  let confidenceTotal = 0;
  let confidenceCount = 0;
  properties.forEach((property) => {
    Object.entries(property.assessments || {}).forEach(([moduleKey, assessment]) => {
      if (!state.modules.has(moduleKey)) return;
      assessments += 1;
      const evidence = Array.isArray(assessment.evidence) ? assessment.evidence.length : 0;
      evidenceRefs += evidence;
      const confidence = Number(assessment.confidence);
      if (Number.isFinite(confidence)) {
        confidenceTotal += confidence;
        confidenceCount += 1;
      }
      if (!moduleCoverage[moduleKey]) {
        moduleCoverage[moduleKey] = {
          module_key: moduleKey,
          module_label: moduleLabels[moduleKey] || moduleKey,
          assessments: 0,
          evidence_references: 0,
          score_coverage_pct: 0,
          evidence_coverage_pct: 0,
          average_confidence: null,
          contacted: 0,
          responses: 0,
          response_rate_pct: 0
        };
      }
      moduleCoverage[moduleKey].assessments += 1;
      moduleCoverage[moduleKey].evidence_references += evidence;
      moduleCoverage[moduleKey].contacted += CONTACTED_STATUSES.has(property.status) ? 1 : 0;
      moduleCoverage[moduleKey].responses += ENGAGED_STATUSES.has(property.status) ? 1 : 0;
    });
  });
  Object.values(moduleCoverage).forEach((row) => {
    row.score_coverage_pct = row.assessments ? 100 : 0;
    row.evidence_coverage_pct = row.assessments ? Math.round((row.evidence_references / row.assessments) * 100) : 0;
    row.response_rate_pct = row.contacted ? Math.round((row.responses / row.contacted) * 100) : 0;
  });
  return {
    status: "pass",
    review_status: evidenceRefs ? "ready" : "review_required",
    scope: {
      tenant_scoped: Boolean(DATA.tenant?.id),
      module_keys: Array.from(state.modules)
    },
    summary: {
      properties: properties.length,
      assessments,
      evidence_references: evidenceRefs,
      source_runs: 0,
      average_confidence: confidenceCount ? confidenceTotal / confidenceCount : null,
      campaign_targets: properties.filter((property) => property.status).length,
      contacted: contactedCount(properties),
      responses: responseCount(properties),
      response_rate_pct: contactedResponseRate(properties),
      latest_timestamp: null,
      timestamp_coverage_pct: 0,
      review_gap_count: evidenceRefs ? 0 : assessments
    },
    source_runs: [],
    evidence_by_type: evidenceRefs ? [{ type: "dashboard_evidence", count: evidenceRefs }] : [],
    module_coverage: Object.values(moduleCoverage),
    review_gaps: evidenceRefs ? [] : [{ severity: "review", key: "missing_dashboard_evidence", count: assessments }],
    failures: [],
    guardrails: {
      source: "dashboard snapshot fallback",
      tenant_scoped: Boolean(DATA.tenant?.id),
      raw_internal_fields_excluded: true,
      lead_claim_language_required: true,
      opportunity_not_intent_without_response: true,
      cross_customer_learning: "aggregate-only outside this customer package"
    }
  };
}

function sourceLedger(properties) {
  const ledger = DATA.trust.sourceLedger;
  if (ledger && typeof ledger === "object" && ledger.summary && ledger.scope) {
    return ledger;
  }
  return fallbackSourceLedger(properties);
}

function sourceLedgerScore(ledger) {
  const summary = ledger.summary || {};
  const assessments = Math.max(1, Number(summary.assessments || 0));
  const evidenceCoverage = Math.min(30, (Number(summary.evidence_references || 0) / assessments) * 30);
  const confidence = Math.min(25, Number(summary.average_confidence || 0) * 25);
  const sourceRuns = Number(summary.source_runs || 0) ? 15 : 0;
  const timestamps = Math.min(10, Number(summary.timestamp_coverage_pct || 0) / 10);
  const gaps = Math.max(0, 20 - Number(summary.review_gap_count || 0) * 2);
  const failurePenalty = Array.isArray(ledger.failures) ? ledger.failures.length * 20 : 0;
  return Math.max(0, Math.min(100, Math.round(evidenceCoverage + confidence + sourceRuns + timestamps + gaps - failurePenalty)));
}

function formatLedgerValue(value, suffix = "") {
  if (value === null || value === undefined || value === "") return "n/a";
  if (typeof value === "number") return `${Math.round(value * 100) / 100}${suffix}`;
  return `${value}${suffix}`;
}

function renderTrust(properties) {
  const ledger = sourceLedger(properties);
  const summary = ledger.summary || {};
  const scope = ledger.scope || {};
  const score = sourceLedgerScore(ledger);
  const verdict = ledger.status === "fail" ? "Action required" : ledger.review_status === "ready" ? "Ready for buyer review" : "Review before handoff";
  const scopeChip = document.getElementById("trustScopeChip");
  if (!scopeChip) return;
  scopeChip.textContent = `${scope.tenant_scoped ? "Tenant scoped" : "Scope review"} - ${(scope.module_keys || []).length} modules`;

  document.getElementById("trustSummaryCards").innerHTML = [
    ["Evidence refs", summary.evidence_references || 0, `${summary.assessments || 0} assessments`],
    ["Source runs", summary.source_runs || 0, "lineage anchors"],
    ["Confidence", summary.average_confidence === null || summary.average_confidence === undefined ? "n/a" : formatPercent(Number(summary.average_confidence) * 100), "average model/operator score"],
    ["Review gaps", summary.review_gap_count || 0, ledger.review_status || "unknown"]
  ].map(([label, value, detail]) => `
    <div class="trust-card">
      <span>${label}</span>
      <strong>${value}</strong>
      <small>${detail}</small>
    </div>
  `).join("");

  document.getElementById("trustVerdictLabel").textContent = verdict;
  document.getElementById("trustVerdictMeter").innerHTML = `
    <div class="trust-ring" style="--trust:${score}"><strong>${score}</strong><span>/100</span></div>
  `;
  const guardrails = ledger.guardrails || {};
  document.getElementById("trustGuardrails").innerHTML = Object.entries(guardrails).map(([key, value]) => {
    const cleanValue = typeof value === "boolean" ? (value ? "yes" : "no") : value;
    return `<div><span>${key.replaceAll("_", " ")}</span><strong>${cleanValue}</strong></div>`;
  }).join("");

  const moduleRows = (ledger.module_coverage || []).filter((row) => state.modules.has(row.module_key));
  document.getElementById("trustModuleCoverage").innerHTML = moduleRows.length ? `
    <div class="coverage-row header"><span>Module</span><span>Assessments</span><span>Evidence</span><span>Score coverage</span><span>Response</span></div>
    ${moduleRows.map((row) => `
      <div class="coverage-row">
        <strong>${row.module_label || moduleLabels[row.module_key] || row.module_key}</strong>
        <span>${row.assessments || 0}</span>
        <span>${row.evidence_references || 0}</span>
        <span>${formatLedgerValue(row.score_coverage_pct, "%")}</span>
        <span>${formatLedgerValue(row.response_rate_pct, "%")}</span>
      </div>
    `).join("")}
  ` : `<div class="empty-state">No module coverage for this filter</div>`;

  document.getElementById("trustSourceRuns").innerHTML = (ledger.source_runs || []).length
    ? ledger.source_runs.map((item) => `
      <div class="source-run-item">
        <strong>${item.source_run_id}</strong>
        <span>${item.assessments} assessments</span>
      </div>
    `).join("")
    : `<div class="empty-state">No source runs in this snapshot</div>`;

  document.getElementById("trustEvidenceTypes").innerHTML = (ledger.evidence_by_type || []).length
    ? ledger.evidence_by_type.map((item) => `
      <div class="evidence-type-item">
        <span>${item.type}</span>
        <strong>${item.count}</strong>
      </div>
    `).join("")
    : `<div class="empty-state">No evidence references available</div>`;

  const gaps = [...(ledger.review_gaps || []), ...(ledger.failures || []).map((failure) => ({ key: failure, count: 1, severity: "fail" }))];
  document.getElementById("trustReviewGaps").innerHTML = gaps.length
    ? gaps.map((gap) => `
      <div class="review-gap-item ${gap.severity === "fail" ? "fail" : "review"}">
        <strong>${String(gap.key).replaceAll("_", " ")}</strong>
        <span>${gap.count || 1}</span>
      </div>
    `).join("")
    : `<div class="review-gap-item pass"><strong>No review gaps detected</strong><span>pass</span></div>`;
}

function asList(value) {
  return Array.isArray(value) ? value : [];
}

function safeScore(value) {
  const score = Number(value);
  return Number.isFinite(score) ? score.toFixed(1) : "n/a";
}

function scoreWidth(value) {
  const score = Math.max(0, Math.min(100, Number(value) || 0));
  return `${score}%`;
}

function humanizeKey(value) {
  return String(value || "")
    .replaceAll("__", " | ")
    .replaceAll("_", " ")
    .replaceAll("=", ": ");
}

function renderLabMetric({ label, value, detail, tone = "" }) {
  return `
    <div class="intelligence-cockpit-metric ${escapeHtml(tone)}">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
      <small>${escapeHtml(detail)}</small>
    </div>
  `;
}

function renderIntelligenceCockpit(lab) {
  const cockpit = document.getElementById("intelligenceLabCockpit");
  if (!cockpit) return;
  const lead = leadPriorityPlan();
  const assignment = partnerAssignmentPlan();
  const segmentation = campaignSegmentationPlan();
  const message = messageStrategyPlan();
  const leadQuality = lead.priority_quality || {};
  const assignmentQuality = assignment.assignment_quality || {};
  const segmentQuality = segmentation.segment_quality || {};
  const messageQuality = message.message_quality || {};
  const partnerId = state.partnerId !== "all" ? state.partnerId : "";
  const partner = partnerId ? activePartner() : null;
  const partnerName = partner?.name || "All partners";
  const queueRows = asList(lead.best_queue);
  const assignmentRows = asList(assignment.best_assignment)
    .filter((row) => !partnerId || String(row.partner_id) === partnerId);
  const segmentRows = asList(segmentation.best_segments)
    .filter((row) => !partnerId || Object.prototype.hasOwnProperty.call(row.partner_mix || {}, partnerId));
  const segmentKeys = new Set(segmentRows.map((row) => row.segment_key).filter(Boolean));
  const messageRows = asList(message.best_message_tests)
    .filter((row) => !partnerId || segmentKeys.has(row.segment_key));
  const families = asList(lab.experiment_families);
  const readyCount = families.filter((row) => row.status === "ready").length;
  const statusChip = document.getElementById("intelligenceLabStatus");
  if (statusChip) {
    statusChip.textContent = partnerId
      ? `${partnerName} scope`
      : readyCount ? `${readyCount} research loops ready` : "Baseline evidence";
  }

  document.getElementById("intelligenceCockpitMetrics").innerHTML = [
    {
      label: "Priority model",
      value: safeScore(leadQuality.final_score),
      detail: `${queueRows.length || 0} review rows`,
      tone: "priority"
    },
    {
      label: "Partner wave",
      value: safeScore(assignmentQuality.final_score),
      detail: `${assignmentRows.length || 0} visible partners, leakage ${assignmentQuality.scope_leakage_count ?? 0}`,
      tone: "scope"
    },
    {
      label: "Segments",
      value: safeScore(segmentQuality.final_score),
      detail: `${segmentRows.length || 0} segments, ${segmentQuality.response_denominator || "contacted_count"}`,
      tone: "segment"
    },
    {
      label: "Messages",
      value: safeScore(messageQuality.final_score),
      detail: `${messageQuality.compliance_pass_rate_pct ?? 0}% compliant, ${messageQuality.forbidden_claim_count ?? 0} blocked claims`,
      tone: "message"
    }
  ].map(renderLabMetric).join("");

  document.getElementById("intelligencePartnerWaves").innerHTML = assignmentRows.length
    ? assignmentRows.slice(0, 6).map((row) => `
      <div class="intelligence-wave-item">
        <div>
          <strong>${escapeHtml(row.partner_name || row.partner_id || "Partner")}</strong>
          <span>${escapeHtml(row.territory || row.recommended_wave || "first review wave")}</span>
        </div>
        <div class="intelligence-meter" aria-hidden="true"><i style="width:${scoreWidth(row.avg_assignment_score)}"></i></div>
        <div class="intelligence-wave-stats">
          <b>${escapeHtml(row.selected_count || 0)} records</b>
          <small>${escapeHtml(formatEuro(row.pipeline_value || 0))} pipeline</small>
          <small>${escapeHtml(row.scope || "assigned_records_only")}</small>
        </div>
      </div>
    `).join("")
    : `<div class="empty-state">No partner wave evidence for ${escapeHtml(partnerName)}</div>`;

  document.getElementById("intelligenceSegments").innerHTML = segmentRows.length
    ? segmentRows.slice(0, 4).map((row) => `
      <div class="intelligence-segment-item">
        <strong>${escapeHtml(humanizeKey(row.segment_label || row.segment_key || "segment"))}</strong>
        <span>${escapeHtml(row.property_count || 0)} records - ${escapeHtml(row.response_rate_pct ?? 0)}% response proxy against ${escapeHtml(row.response_denominator || "contacted_count")}</span>
        <small>${escapeHtml((row.segment_reasons || []).slice(0, 2).join(" / ") || "reviewable segment")}</small>
      </div>
    `).join("")
    : `<div class="empty-state">No segment evidence for ${escapeHtml(partnerName)}</div>`;

  document.getElementById("intelligenceMessageTests").innerHTML = messageRows.length
    ? messageRows.slice(0, 4).map((row) => `
      <div class="intelligence-message-item">
        <div>
          <strong>${escapeHtml(row.subject_theme || row.angle || "Message test")}</strong>
          <span>${escapeHtml(row.opening_line || "Draft requires review")}</span>
        </div>
        <b>${escapeHtml(row.compliance_status || "review")}</b>
      </div>
    `).join("")
    : `<div class="empty-state">No message test evidence for ${escapeHtml(partnerName)}</div>`;
}

function renderIntelligenceImpact(planner) {
  const status = document.getElementById("intelligenceImpactStatus");
  if (!status) return;
  const summary = planner.impact_summary || {};
  const lanes = asList(planner.activation_lanes);
  const channels = asList(planner.channel_mix);
  const stages = asList(planner.measurement_loop);
  status.textContent = planner.status ? humanizeKey(planner.status) : "Review plan";

  document.getElementById("intelligenceImpactMetrics").innerHTML = [
    ["Top queue", summary.top_opportunity_count ?? 0, `${formatEuro(summary.top_pipeline_value || 0)} pipeline`],
    ["No response", summary.no_response_count ?? 0, "clean retest backlog"],
    ["Segments", summary.segment_count ?? 0, `${summary.message_test_count ?? 0} message tests`],
    ["Partner batches", summary.partner_batches ?? 0, `${summary.public_context_coverage_pct ?? 0}% public context`]
  ].map(([label, value, detail]) => `
    <div class="intelligence-impact-metric">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
      <small>${escapeHtml(detail)}</small>
    </div>
  `).join("");

  document.getElementById("intelligenceImpactLanes").innerHTML = lanes.length
    ? lanes.slice(0, 5).map((lane) => `
      <div class="intelligence-impact-lane">
        <div>
          <strong>${escapeHtml(humanizeKey(lane.lane_key || "activation lane"))}</strong>
          <span>${escapeHtml(lane.audience || "review audience")}</span>
        </div>
        <b>${escapeHtml(lane.record_count ?? 0)}</b>
        <small>${escapeHtml(lane.recommended_channel || "review channel")}</small>
        <em>${escapeHtml(lane.guardrail || "review before activation")}</em>
      </div>
    `).join("")
    : `<div class="empty-state">No marketing impact lanes attached</div>`;

  document.getElementById("intelligenceChannelMix").innerHTML = channels.length
    ? channels.slice(0, 5).map((channel) => `
      <div class="intelligence-channel-item">
        <strong>${escapeHtml(humanizeKey(channel.channel || "channel"))}</strong>
        <span>${escapeHtml(channel.role || "review role")}</span>
        <small>${escapeHtml(channel.blocked_until || "approval required")}</small>
      </div>
    `).join("")
    : `<div class="empty-state">No channel mix attached</div>`;

  document.getElementById("intelligenceMeasurementLoop").innerHTML = stages.length
    ? stages.slice(0, 5).map((stage) => `
      <div class="intelligence-measurement-item">
        <strong>${escapeHtml(humanizeKey(stage.stage || "measurement stage"))}</strong>
        <span>${escapeHtml(stage.denominator || "scoped denominator")}</span>
        <small>${escapeHtml(stage.output || "review output")}</small>
      </div>
    `).join("")
    : `<div class="empty-state">No measurement loop attached</div>`;
}

function renderIntelligenceBoardroomBrief(brief) {
  const panel = document.getElementById("intelligenceDecisionBrief");
  if (!panel) return;
  const status = document.getElementById("intelligenceBriefStatus");
  const summary = brief && typeof brief.summary === "object" ? brief.summary : {};
  const decisions = asList(brief?.decision_questions);
  if (status) {
    status.textContent = brief?.status ? humanizeKey(brief.status) : "Buyer review";
  }

  document.getElementById("intelligenceBriefSummary").innerHTML = [
    ["Top opportunities", summary.top_opportunity_count ?? "n/a", "first-wave focus"],
    ["Partner scopes", summary.partner_count ?? "n/a", `${summary.partner_batches ?? 0} batches`],
    ["Segments", summary.segment_count ?? "n/a", `${summary.message_test_count ?? 0} message tests`],
    ["Launch position", summary.launch_position ? humanizeKey(summary.launch_position) : "buyer review", "proof gated"]
  ].map(([label, value, detail]) => `
    <div class="intelligence-brief-metric">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
      <small>${escapeHtml(detail)}</small>
    </div>
  `).join("");

  document.getElementById("intelligenceDecisionMatrix").innerHTML = decisions.length
    ? decisions.slice(0, 5).map((decision) => `
      <div class="intelligence-decision-item">
        <div>
          <strong>${escapeHtml(decision.boardroom_question || humanizeKey(decision.decision_key || "decision"))}</strong>
          <span>${escapeHtml(decision.what_daw_learns || "reviewable evidence attached")}</span>
        </div>
        <div>
          <small>Action</small>
          <b>${escapeHtml(decision.recommended_action || "review with customer owner")}</b>
        </div>
        <div>
          <small>Blocked until</small>
          <em>${escapeHtml(decision.blocked_until || "live proof and customer approval")}</em>
        </div>
        <p>${escapeHtml(decision.guardrail || "review evidence only")}</p>
      </div>
    `).join("")
    : `<div class="empty-state">No boardroom decision brief attached</div>`;
}

function renderIntelligence(properties) {
  const target = document.getElementById("intelligenceModelName");
  if (!target) return;
  const plan = openIntelligencePlan();
  const model = plan.model_card || {};
  const lab = plan.model_lab || {};
  const room = plan.data_collaboration_room || {};
  const planner = plan.marketing_impact_planner || {};
  const brief = plan.boardroom_brief || {};
  const activation = plan.activation || {};
  const outcomes = plan.outcomes || {};
  const input = model.input_summary || {};
  const currentMetrics = outcomes.current_snapshot_metrics || {};
  const modelName = model.name || `${DATA.tenant?.name || "HomePilot"} Opportunity Model`;
  const tenant = model.tenant || {};

  target.textContent = modelName;
  document.getElementById("intelligenceModelMeta").textContent = [
    tenant.producer_network ? "producer network" : "tenant model",
    (tenant.modules || DATA.tenant?.modules || []).join(", "),
    tenant.partner_count ? `${tenant.partner_count} partners` : ""
  ].filter(Boolean).join(" - ") || "Tenant-scoped renovation intelligence";

  document.getElementById("intelligenceScoreStrip").innerHTML = [
    ["Visible records", input.visible_properties ?? properties.length, "tenant scoped"],
    ["Avg score", input.average_best_score ?? "n/a", "best module"],
    ["Pipeline", formatEuro(input.estimated_pipeline_value || 0), "estimated"],
    ["Public context", `${input.public_context_coverage_pct ?? 0}%`, "coverage"]
  ].map(([label, value, detail]) => `
    <div>
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
      <small>${escapeHtml(detail)}</small>
    </div>
  `).join("");

  const signals = Array.isArray(model.signals_used) ? model.signals_used : [];
  document.getElementById("intelligenceModelSignals").innerHTML = signals.length
    ? signals.map((signal) => `<span>${escapeHtml(signal)}</span>`).join("")
    : `<div class="empty-state">No model signals attached to this snapshot</div>`;

  const prohibited = Array.isArray(model.prohibited_decisions) ? model.prohibited_decisions : [];
  document.getElementById("intelligenceModelGuardrails").innerHTML = prohibited.length
    ? prohibited.map((item) => `<div><span>${escapeHtml(item)}</span><strong>blocked</strong></div>`).join("")
    : `<div><span>Opportunity language only</span><strong>active</strong></div>`;

  renderIntelligenceCockpit(lab);
  renderIntelligenceBoardroomBrief(brief);
  renderIntelligenceImpact(planner);

  const families = Array.isArray(lab.experiment_families) ? lab.experiment_families : [];
  document.getElementById("intelligenceLab").innerHTML = families.length
    ? families.map((family) => {
      const score = family.best_score ?? family.score ?? "n/a";
      return `
        <div class="intelligence-lab-item">
          <span>${escapeHtml(family.family || "experiment")}</span>
          <strong>${escapeHtml(score)}</strong>
          <small>${escapeHtml(family.model || family.best_tag || family.status || "review")}</small>
          <b>${escapeHtml(family.evidence_type || "review evidence")}</b>
        </div>
      `;
    }).join("")
    : `<div class="empty-state">No autoresearch evidence attached yet</div>`;

  const sources = Array.isArray(room.sources) ? room.sources : [];
  document.getElementById("intelligenceDataRoom").innerHTML = sources.length
    ? sources.map((source) => `
      <div class="intelligence-source-item">
        <strong>${escapeHtml(source.source || "source")}</strong>
        <span>${escapeHtml(source.allowed_use || "review use")}</span>
        <small>${escapeHtml(source.scope || source.status || "tenant scoped")}</small>
      </div>
    `).join("")
    : `<div class="empty-state">No data room sources attached</div>`;

  const activationItems = Array.isArray(activation.available_surfaces) ? activation.available_surfaces : [];
  document.getElementById("intelligenceActivation").innerHTML = activationItems.length
    ? activationItems.slice(0, 6).map((item) => `<div><span>${escapeHtml(item)}</span><strong>ready</strong></div>`).join("")
    : `<div><span>Customer dashboard priority queue</span><strong>ready</strong></div>`;

  const outcomeRows = [
    ["Response rate", `${currentMetrics.response_rate_pct ?? 0}%`],
    ["Appointment rate", `${currentMetrics.appointment_rate_pct ?? 0}%`],
    ["No-response backlog", currentMetrics.no_response_count ?? 0],
    ["Learning status", outcomes.status || "demo_proxy_ready"]
  ];
  document.getElementById("intelligenceOutcomes").innerHTML = outcomeRows.map(([label, value]) => `
    <div>
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `).join("");
}

function summarizeNetworkProperties(properties) {
  const top = properties.filter((property) => {
    const best = bestAssessment(property);
    return best && (best.grade === "A" || best.grade === "A+");
  });
  const responded = responseCount(properties);
  const appointments = conversionCount(properties);
  const weightedValue = properties.reduce((sum, property) => {
    const best = bestAssessment(property);
    const weight = best ? Math.max(0.25, best.score / 100) : 0;
    return sum + propertyValue(property) * weight;
  }, 0);
  return {
    properties: properties.length,
    top: top.length,
    responded,
    appointments,
    responseRate: contactedResponseRate(properties),
    value: weightedValue,
    facadeM2: properties.reduce((sum, property) => sum + estimatedFacadeM2(property), 0)
  };
}

function propertiesForPartner(partnerId) {
  return DATA.properties.filter((property) => {
    if (!bestAssessment(property)) return false;
    return partnerId === "all" || propertyPartnerId(property) === String(partnerId);
  });
}

function renderNetworkPanel(properties) {
  const panel = document.getElementById("networkPanel");
  if (!panel) return;
  const partners = networkPartners();
  if (!DATA.network || !partners.length) {
    panel.hidden = true;
    return;
  }

  panel.hidden = false;
  const producerName = DATA.network.producer?.name || "Producer network";
  const partner = activePartner();
  const summary = summarizeNetworkProperties(properties);
  document.getElementById("networkTitle").textContent = `${producerName} partner cockpit`;
  document.getElementById("networkScopeChip").textContent = partner ? partner.name || partner.id : `${partners.length} partners`;
  document.getElementById("networkSummary").innerHTML = [
    ["Visible records", summary.properties, partner ? "partner cutdown" : "network scope"],
    ["A/A+ targets", summary.top, `${Math.round(summary.facadeM2).toLocaleString("en-US")} facade m2`],
    ["Response proof", formatPercent(summary.responseRate), `${summary.responded} replies or meetings`],
    ["Weighted pipeline", formatEuro(summary.value), `${summary.appointments} appointments`]
  ].map(([label, value, detail]) => `
    <div class="network-stat">
      <span>${label}</span>
      <strong>${value}</strong>
      <small>${detail}</small>
    </div>
  `).join("");

  document.getElementById("partnerGrid").innerHTML = partners.map((item) => {
    const partnerProperties = propertiesForPartner(item.id);
    const partnerSummary = summarizeNetworkProperties(partnerProperties);
    const selected = String(item.id) === String(state.partnerId);
    return `
      <button class="partner-card ${selected ? "active" : ""}" type="button" data-partner="${escapeHtml(item.id)}">
        <span>${escapeHtml(item.region || item.territory || "Territory")}</span>
        <strong>${escapeHtml(item.name || item.id)}</strong>
        <small>${partnerSummary.properties} records - ${partnerSummary.top} A/A+ - ${formatPercent(partnerSummary.responseRate)}</small>
        <b>${formatEuro(partnerSummary.value)}</b>
      </button>
    `;
  }).join("");
}

function renderExecutive(properties) {
  const target = document.getElementById("decisionLedger");
  if (!target) return;
  const top = properties.filter((property) => {
    const best = bestAssessment(property);
    return best && (best.grade === "A" || best.grade === "A+");
  });
  const responded = responseCount(properties);
  const appointments = conversionCount(properties);
  const noResponse = responseStatus(properties, "no_response");
  const weightedValue = properties.reduce((sum, property) => {
    const best = bestAssessment(property);
    const weight = best ? Math.max(0.25, best.score / 100) : 0;
    return sum + propertyValue(property) * weight;
  }, 0);
  const trust = trustMetrics(properties);
  const responseRate = contactedResponseRate(properties);
  const topShare = properties.length ? (top.length / properties.length) * 100 : 0;

  document.getElementById("executiveScope").textContent = `${networkScopeLabel()} - ${properties.length} records`;
  target.innerHTML = [
    { label: "Weighted pipeline", value: formatEuro(weightedValue), detail: `${top.length} A/A+ opportunities`, tone: "value" },
    { label: "Response proof", value: formatPercent(responseRate), detail: `${responded} replies or meetings`, tone: "proof" },
    { label: "Top share", value: formatPercent(topShare), detail: "A and A+ in filtered set", tone: "quality" },
    { label: "Follow-up risk", value: String(noResponse), detail: "No-response records", tone: noResponse ? "risk" : "proof" }
  ].map((item) => `
    <div class="ledger-item ${item.tone}">
      <span>${item.label}</span>
      <strong>${item.value}</strong>
      <small>${item.detail}</small>
    </div>
  `).join("");

  const trustLabel = trust.score >= 82 ? "Ready for review" : trust.score >= 64 ? "Review before handoff" : "Needs cleanup";
  document.getElementById("trustLabel").textContent = trustLabel;
  document.getElementById("trustMeter").innerHTML = `
    <div class="trust-ring" style="--trust:${trust.score}"><strong>${trust.score}</strong><span>/100</span></div>
  `;
  document.getElementById("trustSignals").innerHTML = [
    ["Geocoded", `${trust.geocoded}/${properties.length}`],
    ["Public context", `${publicContextCoverage(properties)}/${properties.length}`],
    ["Next actions", `${trust.withNextAction}/${properties.length}`],
    ["Response history", `${trust.withInteractions}/${properties.length}`],
    ["Avg confidence", formatPercent(trust.confidence)]
  ].map(([label, value]) => `<div><span>${label}</span><strong>${value}</strong></div>`).join("");

  const shortlist = properties.slice().sort((a, b) => {
    const scoreA = bestAssessment(a)?.score || 0;
    const scoreB = bestAssessment(b)?.score || 0;
    return scoreB - scoreA;
  }).slice(0, 5);
  document.getElementById("executiveShortlist").innerHTML = shortlist.map((property, index) => {
    const best = bestAssessment(property);
    const tags = (property.tags || []).slice(0, 3).map((tag) => `<span>${tag}</span>`).join("");
    return `
      <button class="shortlist-row" data-property="${property.id}">
        <span class="rank">${String(index + 1).padStart(2, "0")}</span>
        <span>
          <strong>${property.address}</strong>
          <small>${moduleLabels[best.key] || best.key} - ${best.label} - ${property.status.replace("_", " ")}</small>
        </span>
        <span class="shortlist-tags">${tags}</span>
        <span class="shortlist-score">${best.score}</span>
      </button>
    `;
  }).join("");

  const contacted = contactedCount(properties);
  const readiness = [
    { label: "Tenant scope", status: DATA.tenant?.id ? "pass" : "review", detail: DATA.tenant?.name || "No tenant" },
    { label: "Export set", status: properties.length ? "pass" : "review", detail: `${properties.length} rows visible` },
    { label: "Campaign evidence", status: responded || appointments ? "pass" : "review", detail: `${responded} response signals` },
    { label: "Retention review", status: contacted ? "review" : "pass", detail: `${contacted} contacted records` },
    { label: "Data trust", status: trust.score >= 82 ? "pass" : "review", detail: `${trust.score}/100` }
  ];
  document.getElementById("executiveReadiness").innerHTML = readiness.map((item) => `
    <div class="readiness-item ${item.status}">
      <span>${item.label}</span>
      <strong>${item.status}</strong>
      <small>${item.detail}</small>
    </div>
  `).join("");

  const objections = {};
  properties.forEach((property) => {
    (property.objections || []).forEach((objection) => {
      objections[objection] = (objections[objection] || 0) + 1;
    });
  });
  const objectionText = Object.entries(objections)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)
    .map(([label, count]) => `${label} (${count})`);
  const learningItems = [
    ...DATA.recommendations.slice(0, 3),
    objectionText.length ? `Main objections: ${objectionText.join(", ")}.` : "No objections in the filtered set."
  ];
  document.getElementById("executiveLearnings").innerHTML = learningItems.map((item) => `
    <div class="learning-item">${item}</div>
  `).join("");
}

function setView(view) {
  state.view = view;
  document.querySelectorAll(".nav-tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
  });
  document.querySelectorAll(".view-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === view);
  });
  render();
  window.requestAnimationFrame(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  });
}

function renderMetrics(properties) {
  const top = properties.filter((property) => {
    const best = bestAssessment(property);
    return best && (best.grade === "A" || best.grade === "A+");
  });
  const value = properties.reduce((sum, property) => {
    const best = bestAssessment(property);
    const weight = best ? Math.max(0.25, best.score / 100) : 0;
    return sum + propertyValue(property) * weight;
  }, 0);

  document.getElementById("metricProperties").textContent = properties.length;
  document.getElementById("metricPropertiesNote").textContent = `${networkScopeLabel()} scope`;
  document.getElementById("metricTop").textContent = top.length;
  document.getElementById("metricResponse").textContent = properties.length
    ? Math.round(contactedResponseRate(properties)) + "%"
    : "0%";
  document.getElementById("metricValue").textContent = formatEuro(value);
}

function renderModuleBars(properties) {
  const modules = Array.from(state.modules);
  const rows = modules.map((key) => {
    const scores = properties
      .map((property) => property.assessments[key]?.score)
      .filter((score) => typeof score === "number");
    const avg = scores.length ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : 0;
    return { key, avg };
  });
  document.getElementById("moduleBars").innerHTML = rows.map((row) => `
    <div class="bar-row">
      <strong>${moduleLabels[row.key] || row.key}</strong>
      <div class="bar-track"><div class="bar-fill" style="width:${row.avg}%"></div></div>
      <span>${row.avg}</span>
    </div>
  `).join("");
}

function renderPriority(properties) {
  const priorities = leadPriorityMap();
  const sorted = properties.slice().sort((a, b) => {
    const priorityA = propertyPriorityScore(a, priorities);
    const priorityB = propertyPriorityScore(b, priorities);
    const bestA = bestAssessment(a)?.score || 0;
    const bestB = bestAssessment(b)?.score || 0;
    return priorityB - priorityA || bestB - bestA;
  }).slice(0, 5);
  document.getElementById("priorityQueue").innerHTML = sorted.map((property) => {
    const best = bestAssessment(property);
    const priority = priorities.get(String(property.id));
    const priorityText = priority
      ? `${Math.round(Number(priority.priority_score) || 0)} priority - ${best.score} ${moduleLabels[best.key]} score`
      : `${best.score} ${moduleLabels[best.key]} score`;
    const reason = Array.isArray(priority?.priority_reasons) && priority.priority_reasons.length
      ? ` - ${escapeHtml(priority.priority_reasons[0])}`
      : "";
    return `
      <button class="priority-item" data-property="${property.id}">
        <strong>${property.address}</strong>
        <small>${priorityText}${reason} - ${property.nextAction}</small>
      </button>
    `;
  }).join("");
}

function renderTable(properties) {
  document.getElementById("propertyTable").innerHTML = properties.map((property) => {
    const best = bestAssessment(property);
    const partnerName = propertyPartnerName(property) || "Tenant";
    const modules = Object.keys(property.assessments || {})
      .filter((key) => state.modules.has(key))
      .map((key) => `<span class="pill">${moduleLabels[key] || key}</span>`)
      .join("");
    const gradeClass = best.grade === "A+" || best.grade === "A" ? "grade-a" : "grade-b";
    return `
      <tr data-property="${property.id}" class="${state.selectedId === property.id ? "selected" : ""}">
        <td><strong>${property.address}</strong><br><small>${property.city}</small></td>
        <td><strong>${escapeHtml(partnerName)}</strong><br><small>${escapeHtml(property.territory || propertyPartner(property).region || "")}</small></td>
        <td>${modules}</td>
        <td>${best.score}</td>
        <td><span class="pill ${gradeClass}">${best.grade}</span></td>
        <td>${property.status.replace("_", " ")}</td>
        <td>${property.nextAction}</td>
      </tr>
    `;
  }).join("");
}

function selectedProperty() {
  const visible = filteredProperties();
  return visible.find((property) => property.id === state.selectedId)
    || visible[0]
    || null;
}

function publicContextCoverage(properties) {
  return properties.filter((property) => {
    const context = property.publicContext || {};
    return Array.isArray(context.features) && context.features.length;
  }).length;
}

function publicFeatureValue(feature) {
  const value = feature?.value ?? "";
  const unit = feature?.unit ? ` ${feature.unit}` : "";
  return `${value}${unit}`.trim() || "Available";
}

function renderPublicContext(property) {
  const target = document.getElementById("publicContextList");
  if (!target) return;
  const context = property?.publicContext || {};
  const features = Array.isArray(context.features) ? context.features : [];
  if (!features.length) {
    target.innerHTML = `<div class="empty-state">No public context attached to this record.</div>`;
    return;
  }
  const meta = [
    context.sourceRunId,
    context.readModel,
    context.licence,
    context.allowedUse
  ].filter(Boolean);
  const featureCards = features.slice(0, 6).map((feature) => `
    <div class="public-context-card">
      <span>${escapeHtml(feature.geographyLevel || "context")}</span>
      <strong>${escapeHtml(feature.label || feature.key || "Public context")}</strong>
      <b>${escapeHtml(publicFeatureValue(feature))}</b>
      <small>${escapeHtml(feature.source || context.attribution || "Source context")}</small>
    </div>
  `).join("");
  const guardrails = Array.isArray(context.guardrails) && context.guardrails.length
    ? `<div class="public-guardrails">${context.guardrails.slice(0, 4).map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>`
    : "";
  target.innerHTML = `
    <div class="public-context-meta">
      ${meta.slice(0, 4).map((item) => `<span>${escapeHtml(item)}</span>`).join("")}
    </div>
    <div class="public-context-grid">${featureCards}</div>
    ${guardrails}
  `;
}

function renderPropertyProfile() {
  const property = selectedProperty();
  if (!property) {
    document.getElementById("propertyTitle").textContent = "No properties yet";
    document.getElementById("propertySubtitle").textContent = "Import a first HomePilot payload to inspect signals, evidence, and follow-up history.";
    document.getElementById("propertyTags").innerHTML = "";
    document.getElementById("assessmentList").innerHTML = "";
    renderPublicContext(null);
    document.getElementById("interactionTimeline").innerHTML = "";
    return;
  }
  document.getElementById("propertyTitle").textContent = property.address;
  const partnerName = propertyPartnerName(property);
  const facadeText = estimatedFacadeM2(property) ? ` - ${Math.round(estimatedFacadeM2(property))} facade m2` : "";
  document.getElementById("propertySubtitle").textContent = `${property.city}${partnerName ? ` - ${partnerName}` : ""} - ${property.status.replace("_", " ")} - weighted value ${formatEuro(propertyValue(property))}${facadeText}`;
  document.getElementById("propertyTags").innerHTML = (property.tags || []).map((tag) => `<span>${tag}</span>`).join("");

  const assessments = Object.entries(property.assessments || {})
    .filter(([key]) => state.modules.has(key))
    .sort((a, b) => b[1].score - a[1].score);
  document.getElementById("assessmentList").innerHTML = assessments.map(([key, item]) => `
    <div class="assessment-card">
      <div>
        <strong>${moduleLabels[key] || key}</strong>
        <small>${item.label} - confidence ${Math.round(item.confidence * 100)}%</small>
      </div>
      <div class="score-ring">${item.score}</div>
    </div>
  `).join("");
  renderPublicContext(property);

  const propertyInteractions = property.interactions || [];
  const timeline = propertyInteractions.length ? propertyInteractions : [
    { date: "Queued", type: "generated", detail: "No interactions logged yet" }
  ];
  document.getElementById("interactionTimeline").innerHTML = timeline.map((item) => `
    <div class="timeline-item">
      <strong>${item.type.replace("_", " ")}</strong>
      <small>${item.date}</small>
      <div>${item.detail}</div>
    </div>
  `).join("");
}

function mapBounds(mapped) {
  return {
    minLat: Math.min(...mapped.map((p) => Number(p.lat))),
    maxLat: Math.max(...mapped.map((p) => Number(p.lat))),
    minLon: Math.min(...mapped.map((p) => Number(p.lon))),
    maxLon: Math.max(...mapped.map((p) => Number(p.lon)))
  };
}

function mapPosition(lat, lon, bounds) {
  return {
    x: 8 + ((Number(lon) - bounds.minLon) / Math.max(0.001, bounds.maxLon - bounds.minLon)) * 84,
    y: 88 - ((Number(lat) - bounds.minLat) / Math.max(0.001, bounds.maxLat - bounds.minLat)) * 76
  };
}

function scoreLevel(score) {
  if (score >= 80) return "high";
  if (score >= 65) return "mid";
  return "low";
}

function clusterProperties(mapped, gridSize = 7) {
  const bounds = mapBounds(mapped);
  const clusters = {};
  mapped.forEach((property) => {
    const best = bestAssessment(property) || { score: 0, key: "" };
    const xIndex = Math.max(0, Math.min(gridSize - 1, Math.floor(((Number(property.lon) - bounds.minLon) / Math.max(0.001, bounds.maxLon - bounds.minLon)) * gridSize)));
    const yIndex = Math.max(0, Math.min(gridSize - 1, Math.floor(((Number(property.lat) - bounds.minLat) / Math.max(0.001, bounds.maxLat - bounds.minLat)) * gridSize)));
    const id = `cell:${xIndex}:${yIndex}`;
    const cluster = clusters[id] || {
      id,
      lat: 0,
      lon: 0,
      count: 0,
      scoreSum: 0,
      maxScore: 0,
      value: 0,
      modules: {},
      topPropertyId: property.id
    };
    cluster.lat += Number(property.lat);
    cluster.lon += Number(property.lon);
    cluster.count += 1;
    cluster.scoreSum += Number(best.score || 0);
    cluster.value += Number(property.estimatedValue || 0);
    cluster.modules[best.key] = (cluster.modules[best.key] || 0) + 1;
    if (Number(best.score || 0) >= cluster.maxScore) {
      cluster.maxScore = Number(best.score || 0);
      cluster.topPropertyId = property.id;
    }
    clusters[id] = cluster;
  });
  return {
    bounds,
    clusters: Object.values(clusters).map((cluster) => ({
      ...cluster,
      lat: cluster.lat / cluster.count,
      lon: cluster.lon / cluster.count,
      avgScore: Math.round(cluster.scoreSum / cluster.count),
      topModule: Object.entries(cluster.modules).sort((a, b) => b[1] - a[1])[0]?.[0] || ""
    })).sort((a, b) => b.count - a.count || b.maxScore - a.maxScore)
  };
}

function renderMap(properties) {
  const mapped = properties.filter((p) => Number.isFinite(Number(p.lat)) && Number.isFinite(Number(p.lon)));
  if (!mapped.length) {
    document.getElementById("opportunityMap").innerHTML = "<div class=\"empty-state\">No geocoded properties in this view</div>";
    return;
  }

  const visualMap = DATA.visualIntelligence?.map || {};
  const clusterThreshold = Number(visualMap.cluster_threshold || 80);
  if (mapped.length > clusterThreshold) {
    const model = clusterProperties(mapped, Number(visualMap.grid_size || 7));
    document.getElementById("opportunityMap").innerHTML = model.clusters.map((cluster) => {
      const position = mapPosition(cluster.lat, cluster.lon, model.bounds);
      const level = scoreLevel(cluster.maxScore);
      const size = Math.max(34, Math.min(76, 28 + cluster.count * 4));
      return `
        <button class="map-cluster ${level}" style="left:${position.x}%;top:${position.y}%;width:${size}px;height:${size}px" data-property="${cluster.topPropertyId}" aria-label="${cluster.count} properties"></button>
        <div class="map-label cluster-label" style="left:${position.x}%;top:${position.y}%">
          <strong>${cluster.count} homes / ${cluster.maxScore}</strong><br>${moduleLabels[cluster.topModule] || cluster.topModule || "Mixed"} cluster
        </div>
      `;
    }).join("");
    return;
  }

  const bounds = mapBounds(mapped);
  document.getElementById("opportunityMap").innerHTML = mapped.map((property) => {
    const best = bestAssessment(property);
    const position = mapPosition(property.lat, property.lon, bounds);
    const level = scoreLevel(best.score);
    return `
      <button class="map-point ${level}" style="left:${position.x}%;top:${position.y}%" data-property="${property.id}" aria-label="${property.address}"></button>
      <div class="map-label" style="left:${position.x}%;top:${position.y}%">
        <strong>${best.score} ${moduleLabels[best.key]}</strong><br>${property.city}
      </div>
    `;
  }).join("");
}

function renderCampaign(properties) {
  const steps = [
    ["generated", "Generated"],
    ["sent", "Sent"],
    ["no_response", "No response"],
    ["responded", "Responded"],
    ["appointment", "Appointment"]
  ];
  document.getElementById("funnel").innerHTML = steps.map(([status, label]) => {
    const count = properties.filter((property) => property.status === status).length;
    const pct = properties.length ? Math.round((count / properties.length) * 100) : 0;
    return `
      <div class="funnel-step">
        <span>${label}</span>
        <strong>${count}</strong>
        <small>${pct}% of filtered set</small>
      </div>
    `;
  }).join("");

  const objections = {};
  properties.forEach((property) => {
    (property.objections || []).forEach((objection) => {
      objections[objection] = (objections[objection] || 0) + 1;
    });
  });
  document.getElementById("objectionCloud").innerHTML = Object.entries(objections).length
    ? Object.entries(objections).map(([label, count]) => `<span>${label} ${count}</span>`).join("")
    : "<span>No objections logged</span>";

  document.getElementById("recommendations").innerHTML = DATA.recommendations
    .map((item) => `<div class="recommendation">${item}</div>`)
    .join("");
}

function fallbackBrain(properties) {
  const nodes = [];
  const edges = [];
  const addNode = (node) => {
    if (!nodes.some((item) => item.id === node.id)) nodes.push(node);
  };
  const addEdge = (edge) => edges.push(edge);
  addNode({ id: "tenant:workspace", label: "Tenant workspace", type: "tenant", weight: properties.length || 1 });
  Array.from(state.modules).forEach((key) => {
    addNode({ id: `module:${key}`, label: moduleLabels[key] || key, type: "module", module_key: key });
    addEdge({ source: "tenant:workspace", target: `module:${key}`, type: "enabled_module", label: "enabled" });
  });
  properties.forEach((property) => {
    const best = bestAssessment(property);
    if (!best) return;
    const propertyNode = `property:${property.id}`;
    const partner = propertyPartner(property);
    if (partner.id) {
      const partnerNode = `partner:${partner.id}`;
      addNode({ id: partnerNode, label: partner.name || partner.id, type: "partner", partner_id: partner.id, region: partner.region });
      addEdge({ source: "tenant:workspace", target: partnerNode, type: "partner_scope", label: "allocates", partner_id: partner.id });
      addEdge({ source: partnerNode, target: propertyNode, type: "assigned_property", label: "assigned", property_id: property.id, partner_id: partner.id });
    }
    addNode({ id: propertyNode, label: property.address, type: "property", property_id: property.id, score: best.score, grade: best.grade, status: property.status });
    addEdge({ source: `module:${best.key}`, target: propertyNode, type: "scores_property", label: "scores", score: best.score });
    addNode({ id: `status:${property.status}`, label: property.status.replace("_", " "), type: "reaction", status: property.status });
    addEdge({ source: propertyNode, target: `status:${property.status}`, type: "campaign_status", label: "status" });
  });
  return { nodes, edges, stats: { nodes: nodes.length, edges: edges.length, properties: properties.length, modules: state.modules.size } };
}

function filteredBrain(properties) {
  const visiblePropertyIds = new Set(properties.map((property) => property.id));
  const visibleModules = new Set(state.modules);
  const source = DATA.brain.nodes.length ? DATA.brain : fallbackBrain(properties);
  const nodes = source.nodes.filter((node) => {
    if (node.property_id && !visiblePropertyIds.has(node.property_id)) return false;
    if (node.module_key && !visibleModules.has(node.module_key)) return false;
    if (state.partnerId !== "all" && node.partner_id && String(node.partner_id) !== state.partnerId) return false;
    return true;
  });
  const nodeIds = new Set(nodes.map((node) => node.id));
  const edges = source.edges.filter((edge) => {
    if (!nodeIds.has(edge.source) || !nodeIds.has(edge.target)) return false;
    if (edge.property_id && !visiblePropertyIds.has(edge.property_id)) return false;
    if (edge.module_key && !visibleModules.has(edge.module_key)) return false;
    if (state.partnerId !== "all" && edge.partner_id && String(edge.partner_id) !== state.partnerId) return false;
    return true;
  });
  const connectedIds = new Set(edges.flatMap((edge) => [edge.source, edge.target]));
  const prunedNodes = nodes.filter((node) => {
    if (connectedIds.has(node.id)) return true;
    return ["tenant", "module", "partner"].includes(node.type);
  });
  const graphPlan = DATA.visualIntelligence?.graph || {};
  const nodeBudget = Number(graphPlan.node_budget || 160);
  const edgeBudget = Number(graphPlan.edge_budget || 260);
  if (prunedNodes.length <= nodeBudget && edges.length <= edgeBudget) {
    return { nodes: prunedNodes, edges };
  }

  const planIds = new Set(Array.isArray(graphPlan.render_node_ids) ? graphPlan.render_node_ids : []);
  const selected = prunedNodes
    .filter((node) => !planIds.size || planIds.has(node.id))
    .slice(0, nodeBudget);
  const selectedIds = new Set(selected.map((node) => node.id));
  const selectedEdges = edges
    .filter((edge) => selectedIds.has(edge.source) && selectedIds.has(edge.target))
    .slice(0, edgeBudget);
  return { nodes: selected, edges: selectedEdges };
}

const BRAIN_WORLD = { width: 1680, height: 920, pad: 72 };
const BRAIN_VIEWBOX = { width: 980, height: 560 };
const BRAIN_LAYOUT_DEFAULTS = {
  worldWidth: 1680,
  worldHeight: 920,
  worldPad: 72,
  tickCount: 150,
  coolingSpan: 170,
  laneForce: 0.018,
  centerGravity: 0.0025,
  edgeBaseDistance: 170,
  edgeSpanFactor: 0.18,
  edgeSpanCap: 90,
  edgeForce: 0.012,
  repulsionPadding: 42,
  repulsionForce: 0.48,
  fitXMargin: 42,
  fitYMargin: 58,
  minScale: 0.34,
  maxScale: 1.15,
  propertyLabelBudget: 10,
  initialStagger: 14,
  initialXJitter: 18,
  lanes: {
    tenant: { x: 100, weight: 1.25 },
    module: { x: 260, weight: 1.1 },
    partner: { x: 445, weight: 1 },
    campaign: { x: 615, weight: 0.9 },
    signal: { x: 790, weight: 0.75 },
    property: { x: 1010, weight: 0.55 },
    reaction: { x: 1260, weight: 0.85 },
    objection: { x: 1330, weight: 0.85 },
    action: { x: 1510, weight: 1 }
  }
};
const graphSession = {
  graph: { nodes: [], edges: [] },
  nodes: [],
  byId: {},
  svg: null,
  viewport: null,
  pan: null,
  drag: null
};

const brainTypeLanes = {
  tenant: { x: 100, weight: 1.25 },
  module: { x: 260, weight: 1.1 },
  partner: { x: 445, weight: 1 },
  campaign: { x: 615, weight: 0.9 },
  signal: { x: 790, weight: 0.75 },
  property: { x: 1010, weight: 0.55 },
  reaction: { x: 1260, weight: 0.85 },
  objection: { x: 1330, weight: 0.85 },
  action: { x: 1510, weight: 1 }
};

function finiteLayoutNumber(value, fallback) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function brainLayoutConfig() {
  const raw = DATA.visualIntelligence?.graph?.layout_config || {};
  const rawLanes = raw.lanes || {};
  const lanes = {};
  Object.entries(BRAIN_LAYOUT_DEFAULTS.lanes).forEach(([key, lane]) => {
    lanes[key] = {
      x: finiteLayoutNumber(rawLanes[key]?.x, lane.x),
      weight: finiteLayoutNumber(rawLanes[key]?.weight, lane.weight)
    };
  });
  return {
    worldWidth: finiteLayoutNumber(raw.world_width, BRAIN_LAYOUT_DEFAULTS.worldWidth),
    worldHeight: finiteLayoutNumber(raw.world_height, BRAIN_LAYOUT_DEFAULTS.worldHeight),
    worldPad: finiteLayoutNumber(raw.world_pad, BRAIN_LAYOUT_DEFAULTS.worldPad),
    tickCount: Math.max(40, Math.round(finiteLayoutNumber(raw.tick_count, BRAIN_LAYOUT_DEFAULTS.tickCount))),
    coolingSpan: finiteLayoutNumber(raw.cooling_span, BRAIN_LAYOUT_DEFAULTS.coolingSpan),
    laneForce: finiteLayoutNumber(raw.lane_force, BRAIN_LAYOUT_DEFAULTS.laneForce),
    centerGravity: finiteLayoutNumber(raw.center_gravity, BRAIN_LAYOUT_DEFAULTS.centerGravity),
    edgeBaseDistance: finiteLayoutNumber(raw.edge_base_distance, BRAIN_LAYOUT_DEFAULTS.edgeBaseDistance),
    edgeSpanFactor: finiteLayoutNumber(raw.edge_span_factor, BRAIN_LAYOUT_DEFAULTS.edgeSpanFactor),
    edgeSpanCap: finiteLayoutNumber(raw.edge_span_cap, BRAIN_LAYOUT_DEFAULTS.edgeSpanCap),
    edgeForce: finiteLayoutNumber(raw.edge_force, BRAIN_LAYOUT_DEFAULTS.edgeForce),
    repulsionPadding: finiteLayoutNumber(raw.repulsion_padding, BRAIN_LAYOUT_DEFAULTS.repulsionPadding),
    repulsionForce: finiteLayoutNumber(raw.repulsion_force, BRAIN_LAYOUT_DEFAULTS.repulsionForce),
    fitXMargin: finiteLayoutNumber(raw.fit_x_margin, BRAIN_LAYOUT_DEFAULTS.fitXMargin),
    fitYMargin: finiteLayoutNumber(raw.fit_y_margin, BRAIN_LAYOUT_DEFAULTS.fitYMargin),
    minScale: finiteLayoutNumber(raw.min_scale, BRAIN_LAYOUT_DEFAULTS.minScale),
    maxScale: finiteLayoutNumber(raw.max_scale, BRAIN_LAYOUT_DEFAULTS.maxScale),
    propertyLabelBudget: Math.max(0, Math.round(finiteLayoutNumber(raw.property_label_budget, BRAIN_LAYOUT_DEFAULTS.propertyLabelBudget))),
    initialStagger: finiteLayoutNumber(raw.initial_stagger, BRAIN_LAYOUT_DEFAULTS.initialStagger),
    initialXJitter: finiteLayoutNumber(raw.initial_x_jitter, BRAIN_LAYOUT_DEFAULTS.initialXJitter),
    lanes
  };
}

function laneForBrainType(type, config) {
  return config.lanes[type] || brainTypeLanes[type] || { x: config.worldWidth / 2, weight: 0.6 };
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function selectorValue(value) {
  return String(value ?? "").replaceAll("\\", "\\\\").replaceAll('"', '\\"');
}

function graphSignature(graph) {
  return [
    graph.nodes.map((node) => node.id).join("|"),
    graph.edges.map((edge) => `${edge.source}>${edge.target}:${edge.type || ""}`).join("|"),
    JSON.stringify(DATA.visualIntelligence?.graph?.layout_config || {})
  ].join("::");
}

function brainRadius(node) {
  if (node.type === "property") return Math.max(18, Math.min(30, Number(node.score || 70) / 3.5));
  if (node.type === "tenant") return 34;
  if (node.type === "module") return 25;
  if (node.type === "partner") return 27;
  return 21;
}

function visibleBrainLabelIds(nodes) {
  const config = brainLayoutConfig();
  return new Set(nodes
    .filter((node) => node.type === "property")
    .sort((a, b) => Number(b.score || 0) - Number(a.score || 0))
    .slice(0, config.propertyLabelBudget)
    .map((node) => node.id));
}

function shouldShowBrainLabel(node, highlightedPropertyIds) {
  if (["tenant", "module", "partner", "campaign", "reaction", "objection", "action"].includes(node.type)) return true;
  return highlightedPropertyIds.has(node.id);
}

function initialBrainPosition(node, typeIndex, typeTotal, index, config) {
  const lane = laneForBrainType(node.type, config);
  const usableHeight = config.worldHeight - config.worldPad * 2;
  const slot = (typeIndex + 0.5) / Math.max(1, typeTotal);
  const stagger = ((index % 5) - 2) * config.initialStagger;
  const y = config.worldPad + slot * usableHeight + stagger;
  return {
    x: Math.max(config.worldPad, Math.min(config.worldWidth - config.worldPad, lane.x + ((index % 3) - 1) * config.initialXJitter)),
    y: Math.max(config.worldPad, Math.min(config.worldHeight - config.worldPad, y))
  };
}

function buildInitialBrainLayout(graph) {
  const config = brainLayoutConfig();
  const byType = {};
  graph.nodes.forEach((node) => {
    byType[node.type] = byType[node.type] || [];
    byType[node.type].push(node.id);
  });
  const layout = {};
  graph.nodes.forEach((node, index) => {
    const ids = byType[node.type] || [node.id];
    const typeIndex = Math.max(0, ids.indexOf(node.id));
    layout[node.id] = {
      ...initialBrainPosition(node, typeIndex, ids.length, index, config),
      r: brainRadius(node),
      pinned: Boolean(state.brain.pinned[node.id])
    };
    if (state.brain.pinned[node.id]) {
      layout[node.id].x = state.brain.pinned[node.id].x;
      layout[node.id].y = state.brain.pinned[node.id].y;
    }
  });
  return relaxBrainLayout(graph, layout);
}

function clampBrainNode(point) {
  const config = brainLayoutConfig();
  point.x = Math.max(config.worldPad, Math.min(config.worldWidth - config.worldPad, point.x));
  point.y = Math.max(config.worldPad, Math.min(config.worldHeight - config.worldPad, point.y));
}

function relaxBrainLayout(graph, layout) {
  const config = brainLayoutConfig();
  const nodes = graph.nodes;
  const edges = graph.edges;
  const nodeIds = new Set(nodes.map((node) => node.id));
  const linkedEdges = edges.filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target));

  for (let tick = 0; tick < config.tickCount; tick += 1) {
    const cooling = Math.max(0, 1 - tick / Math.max(1, config.coolingSpan));
    nodes.forEach((node) => {
      const point = layout[node.id];
      if (!point || point.pinned) return;
      const lane = laneForBrainType(node.type, config);
      point.x += (lane.x - point.x) * config.laneForce * lane.weight * cooling;
      point.y += (config.worldHeight / 2 - point.y) * config.centerGravity * cooling;
    });

    linkedEdges.forEach((edge) => {
      const source = layout[edge.source];
      const target = layout[edge.target];
      if (!source || !target) return;
      const dx = target.x - source.x;
      const dy = target.y - source.y;
      const distance = Math.max(1, Math.hypot(dx, dy));
      const desired = config.edgeBaseDistance + Math.min(config.edgeSpanCap, Math.abs(target.x - source.x) * config.edgeSpanFactor);
      const force = (distance - desired) * config.edgeForce * cooling;
      const nx = dx / distance;
      const ny = dy / distance;
      if (!source.pinned) {
        source.x += nx * force;
        source.y += ny * force;
      }
      if (!target.pinned) {
        target.x -= nx * force;
        target.y -= ny * force;
      }
    });

    for (let i = 0; i < nodes.length; i += 1) {
      for (let j = i + 1; j < nodes.length; j += 1) {
        const a = layout[nodes[i].id];
        const b = layout[nodes[j].id];
        if (!a || !b) continue;
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const distance = Math.max(0.1, Math.hypot(dx, dy));
        const minDistance = a.r + b.r + config.repulsionPadding;
        if (distance >= minDistance) continue;
        const push = ((minDistance - distance) / distance) * config.repulsionForce * cooling;
        const px = dx * push;
        const py = dy * push;
        if (!a.pinned) {
          a.x -= px;
          a.y -= py;
        }
        if (!b.pinned) {
          b.x += px;
          b.y += py;
        }
      }
    }
    nodes.forEach((node) => {
      const point = layout[node.id];
      if (point) clampBrainNode(point);
    });
  }
  return layout;
}

function ensureBrainLayout(graph) {
  const signature = graphSignature(graph);
  if (state.brain.signature !== signature) {
    state.brain.signature = signature;
    state.brain.layout = buildInitialBrainLayout(graph);
    fitBrainToViewport(false);
  } else if (!state.brain.layout) {
    state.brain.layout = buildInitialBrainLayout(graph);
  }
  return state.brain.layout;
}

function pathForBrainEdge(from, to) {
  const dx = Math.max(90, Math.abs(to.x - from.x) * 0.46);
  const c1x = from.x + (to.x >= from.x ? dx : -dx);
  const c2x = to.x - (to.x >= from.x ? dx : -dx);
  return `M ${from.x} ${from.y} C ${c1x} ${from.y}, ${c2x} ${to.y}, ${to.x} ${to.y}`;
}

function applyBrainTransform() {
  if (!graphSession.viewport) return;
  graphSession.viewport.setAttribute("transform", `translate(${state.brain.tx} ${state.brain.ty}) scale(${state.brain.scale})`);
}

function fitBrainToViewport(animate = true) {
  const config = brainLayoutConfig();
  const layout = state.brain.layout || {};
  const points = Object.values(layout);
  if (!points.length) {
    state.brain.scale = 1;
    state.brain.tx = 0;
    state.brain.ty = 0;
    return;
  }
  const minX = Math.min(...points.map((point) => point.x - point.r - config.fitXMargin));
  const maxX = Math.max(...points.map((point) => point.x + point.r + config.fitXMargin));
  const minY = Math.min(...points.map((point) => point.y - point.r - config.fitYMargin));
  const maxY = Math.max(...points.map((point) => point.y + point.r + config.fitYMargin));
  const width = Math.max(1, maxX - minX);
  const height = Math.max(1, maxY - minY);
  const scale = Math.max(config.minScale, Math.min(config.maxScale, Math.min(BRAIN_VIEWBOX.width / width, BRAIN_VIEWBOX.height / height)));
  state.brain.scale = scale;
  state.brain.tx = (BRAIN_VIEWBOX.width - width * scale) / 2 - minX * scale;
  state.brain.ty = (BRAIN_VIEWBOX.height - height * scale) / 2 - minY * scale;
  applyBrainTransform();
  if (animate && graphSession.svg) {
    graphSession.svg.classList.add("is-fitting");
    window.setTimeout(() => graphSession.svg?.classList.remove("is-fitting"), 220);
  }
}

function brainPointFromEvent(svg, event) {
  const rect = svg.getBoundingClientRect();
  return {
    x: ((event.clientX - rect.left) / Math.max(1, rect.width)) * BRAIN_VIEWBOX.width,
    y: ((event.clientY - rect.top) / Math.max(1, rect.height)) * BRAIN_VIEWBOX.height
  };
}

function worldPointFromEvent(svg, event) {
  const point = brainPointFromEvent(svg, event);
  return {
    x: (point.x - state.brain.tx) / state.brain.scale,
    y: (point.y - state.brain.ty) / state.brain.scale
  };
}

function setBrainZoom(nextScale, anchor) {
  const scale = Math.max(0.25, Math.min(2.4, nextScale));
  const point = anchor || { x: BRAIN_VIEWBOX.width / 2, y: BRAIN_VIEWBOX.height / 2 };
  const world = {
    x: (point.x - state.brain.tx) / state.brain.scale,
    y: (point.y - state.brain.ty) / state.brain.scale
  };
  state.brain.scale = scale;
  state.brain.tx = point.x - world.x * scale;
  state.brain.ty = point.y - world.y * scale;
  applyBrainTransform();
}

function updateBrainDom(nodeId) {
  const point = state.brain.layout?.[nodeId];
  if (!point || !graphSession.svg) return;
  const safeNodeId = selectorValue(nodeId);
  const group = graphSession.svg.querySelector(`[data-graph-node="${safeNodeId}"]`);
  if (group) group.setAttribute("transform", `translate(${point.x}, ${point.y})`);
  graphSession.svg.querySelectorAll(`[data-source="${safeNodeId}"], [data-target="${safeNodeId}"]`).forEach((edgeEl) => {
    const from = state.brain.layout?.[edgeEl.dataset.source];
    const to = state.brain.layout?.[edgeEl.dataset.target];
      if (from && to) edgeEl.setAttribute("d", pathForBrainEdge(from, to));
  });
}

function updateBrainSelectionDom() {
  if (!graphSession.svg) return;
  graphSession.svg.querySelectorAll(".brain-node").forEach((node) => {
    node.classList.toggle("selected", node.dataset.graphNode === state.brain.selectedNodeId);
  });
  updateBrainMoveControls();
}

function selectBrainNode(nodeId) {
  state.brain.selectedNodeId = nodeId || "";
  updateBrainSelectionDom();
}

function nudgeSelectedBrainNode(dx, dy) {
  let nodeId = state.brain.selectedNodeId;
  if (!nodeId || !state.brain.layout?.[nodeId]) {
    nodeId = graphSession.nodes.find((node) => node.type === "property")?.id || graphSession.nodes[0]?.id || "";
    state.brain.selectedNodeId = nodeId;
  }
  const point = state.brain.layout?.[nodeId];
  if (!point) return;
  point.x += dx;
  point.y += dy;
  point.pinned = true;
  clampBrainNode(point);
  state.brain.pinned[nodeId] = { x: point.x, y: point.y };
  updateBrainDom(nodeId);
  updateBrainSelectionDom();
}

function updateBrainMoveControls() {
  const moveButton = document.getElementById("brainMoveMode");
  if (moveButton) {
    moveButton.classList.toggle("active", Boolean(state.brain.moveMode));
    moveButton.setAttribute("aria-pressed", state.brain.moveMode ? "true" : "false");
  }
  ["brainNudgeLeft", "brainNudgeUp", "brainNudgeDown", "brainNudgeRight"].forEach((id) => {
    const button = document.getElementById(id);
    if (button) button.disabled = !graphSession.nodes.length;
  });
}

function bindBrainInteractions(svg) {
  if (svg.dataset.brainInteractionsBound === "true") return;
  svg.dataset.brainInteractionsBound = "true";

  svg.addEventListener("wheel", (event) => {
    event.preventDefault();
    const anchor = brainPointFromEvent(svg, event);
    const factor = event.deltaY > 0 ? 0.88 : 1.14;
    setBrainZoom(state.brain.scale * factor, anchor);
  }, { passive: false });

  svg.addEventListener("pointerdown", (event) => {
    if (event.target.closest(".brain-node")) return;
    const start = brainPointFromEvent(svg, event);
    graphSession.pan = { pointerId: event.pointerId, start, tx: state.brain.tx, ty: state.brain.ty };
    svg.setPointerCapture(event.pointerId);
    svg.classList.add("is-panning");
  });

  svg.addEventListener("pointermove", (event) => {
    if (!graphSession.pan || graphSession.pan.pointerId !== event.pointerId) return;
    const point = brainPointFromEvent(svg, event);
    state.brain.tx = graphSession.pan.tx + point.x - graphSession.pan.start.x;
    state.brain.ty = graphSession.pan.ty + point.y - graphSession.pan.start.y;
    applyBrainTransform();
  });

  const endPan = (event) => {
    if (!graphSession.pan || graphSession.pan.pointerId !== event.pointerId) return;
    graphSession.pan = null;
    svg.classList.remove("is-panning");
  };
  svg.addEventListener("pointerup", endPan);
  svg.addEventListener("pointercancel", endPan);

  svg.addEventListener("mousedown", (event) => {
    if (event.button !== 0 || event.target.closest(".brain-node") || graphSession.pan) return;
    event.preventDefault();
    const start = brainPointFromEvent(svg, event);
    graphSession.pan = { pointerId: "mouse", start, tx: state.brain.tx, ty: state.brain.ty };
    svg.classList.add("is-panning");

    const movePan = (moveEvent) => {
      if (!graphSession.pan || graphSession.pan.pointerId !== "mouse") return;
      const point = brainPointFromEvent(svg, moveEvent);
      state.brain.tx = graphSession.pan.tx + point.x - graphSession.pan.start.x;
      state.brain.ty = graphSession.pan.ty + point.y - graphSession.pan.start.y;
      applyBrainTransform();
    };
    const stopPan = () => {
      if (graphSession.pan?.pointerId === "mouse") graphSession.pan = null;
      svg.classList.remove("is-panning");
      window.removeEventListener("mousemove", movePan);
      window.removeEventListener("mouseup", stopPan);
    };
    window.addEventListener("mousemove", movePan);
    window.addEventListener("mouseup", stopPan);
  });
}

function bindBrainNodeDrag(group) {
  group.addEventListener("pointerdown", (event) => {
    event.stopPropagation();
    const nodeId = group.dataset.graphNode;
    const point = state.brain.layout?.[nodeId];
    if (!point) return;
    const start = worldPointFromEvent(graphSession.svg, event);
    graphSession.drag = {
      pointerId: event.pointerId,
      nodeId,
      start,
      x: point.x,
      y: point.y,
      moved: false
    };
    group.setPointerCapture(event.pointerId);
    group.classList.add("is-dragging");
  });

  group.addEventListener("pointermove", (event) => {
    const drag = graphSession.drag;
    if (!drag || drag.pointerId !== event.pointerId || drag.nodeId !== group.dataset.graphNode) return;
    const point = worldPointFromEvent(graphSession.svg, event);
    const dx = point.x - drag.start.x;
    const dy = point.y - drag.start.y;
    if (Math.hypot(dx, dy) > 3) drag.moved = true;
    const layoutPoint = state.brain.layout[drag.nodeId];
    layoutPoint.x = drag.x + dx;
    layoutPoint.y = drag.y + dy;
    layoutPoint.pinned = true;
    clampBrainNode(layoutPoint);
    state.brain.pinned[drag.nodeId] = { x: layoutPoint.x, y: layoutPoint.y };
    updateBrainDom(drag.nodeId);
  });

  const endDrag = (event) => {
    const drag = graphSession.drag;
    if (!drag || drag.pointerId !== event.pointerId || drag.nodeId !== group.dataset.graphNode) return;
    group.classList.remove("is-dragging");
    graphSession.drag = null;
    if (!drag.moved && group.dataset.property) {
      if (state.brain.moveMode) {
        selectBrainNode(group.dataset.graphNode);
      } else {
        state.selectedId = group.dataset.property;
        setView("property");
      }
    }
  };
  group.addEventListener("pointerup", endDrag);
  group.addEventListener("pointercancel", endDrag);

  group.addEventListener("mousedown", (event) => {
    if (event.button !== 0 || graphSession.drag) return;
    event.preventDefault();
    event.stopPropagation();
    const nodeId = group.dataset.graphNode;
    const point = state.brain.layout?.[nodeId];
    if (!point) return;
    const start = worldPointFromEvent(graphSession.svg, event);
    graphSession.drag = {
      pointerId: "mouse",
      nodeId,
      start,
      x: point.x,
      y: point.y,
      moved: false
    };
    group.classList.add("is-dragging");

    const moveDrag = (moveEvent) => {
      const drag = graphSession.drag;
      if (!drag || drag.pointerId !== "mouse" || drag.nodeId !== group.dataset.graphNode) return;
      const movePoint = worldPointFromEvent(graphSession.svg, moveEvent);
      const dx = movePoint.x - drag.start.x;
      const dy = movePoint.y - drag.start.y;
      if (Math.hypot(dx, dy) > 3) drag.moved = true;
      const layoutPoint = state.brain.layout[drag.nodeId];
      layoutPoint.x = drag.x + dx;
      layoutPoint.y = drag.y + dy;
      layoutPoint.pinned = true;
      clampBrainNode(layoutPoint);
      state.brain.pinned[drag.nodeId] = { x: layoutPoint.x, y: layoutPoint.y };
      updateBrainDom(drag.nodeId);
    };

    const stopDrag = () => {
      const drag = graphSession.drag;
      if (!drag || drag.pointerId !== "mouse" || drag.nodeId !== group.dataset.graphNode) return;
      group.classList.remove("is-dragging");
      graphSession.drag = null;
      window.removeEventListener("mousemove", moveDrag);
      window.removeEventListener("mouseup", stopDrag);
      if (!drag.moved && group.dataset.property) {
        if (state.brain.moveMode) {
          selectBrainNode(group.dataset.graphNode);
        } else {
          state.selectedId = group.dataset.property;
          setView("property");
        }
      }
    };

    window.addEventListener("mousemove", moveDrag);
    window.addEventListener("mouseup", stopDrag);
  });

  group.addEventListener("click", (event) => {
    if (!state.brain.moveMode || graphSession.drag) return;
    event.preventDefault();
    event.stopPropagation();
    selectBrainNode(group.dataset.graphNode);
  });
}

function renderBrainStats(graph) {
  const stats = {
    nodes: graph.nodes.length,
    edges: graph.edges.length,
    properties: graph.nodes.filter((node) => node.type === "property").length,
    signals: graph.nodes.filter((node) => node.type === "signal").length,
    reactions: graph.nodes.filter((node) => ["reaction", "objection"].includes(node.type)).length
  };
  const target = document.getElementById("brainStats");
  if (!target) return;
  target.innerHTML = `
    <div><strong>${stats.properties}</strong><span>Properties</span></div>
    <div><strong>${stats.signals}</strong><span>Signals</span></div>
    <div><strong>${stats.reactions}</strong><span>Reactions</span></div>
    <div><strong>${stats.edges}</strong><span>Links</span></div>
  `;
}

function renderBrainLegend() {
  const target = document.getElementById("brainLegend");
  if (!target) return;
  target.innerHTML = ["module", "partner", "campaign", "signal", "property", "reaction", "objection", "action"]
    .map((type) => `<span><i class="brain-dot ${type}"></i>${type.replace("_", " ")}</span>`)
    .join("");
}

function renderBrain(properties) {
  const svg = document.getElementById("brainGraph");
  const graph = filteredBrain(properties);
  renderBrainStats(graph);
  renderBrainLegend();
  if (!graph.nodes.length) {
    graphSession.graph = { nodes: [], edges: [] };
    graphSession.nodes = [];
    graphSession.byId = {};
    svg.innerHTML = `<text x="490" y="260" text-anchor="middle" class="brain-empty">No graph data for this filter</text>`;
    return;
  }

  svg.setAttribute("viewBox", `0 0 ${BRAIN_VIEWBOX.width} ${BRAIN_VIEWBOX.height}`);
  const layout = ensureBrainLayout(graph);
  const positioned = graph.nodes.map((node) => ({
    ...node,
    ...(layout[node.id] || { x: BRAIN_WORLD.width / 2, y: BRAIN_WORLD.height / 2, r: brainRadius(node) })
  }));
  const byId = Object.fromEntries(positioned.map((node) => [node.id, node]));
  graphSession.graph = graph;
  graphSession.nodes = positioned;
  graphSession.byId = byId;

  const edgeMarkup = graph.edges.map((edge, index) => {
    const from = layout[edge.source];
    const to = layout[edge.target];
    if (!from || !to) return "";
    const width = Math.max(1, Math.min(5, Number(edge.weight || 1)));
    return `
      <path class="brain-edge ${edge.type || "link"}" data-source="${escapeHtml(edge.source)}" data-target="${escapeHtml(edge.target)}" data-edge="${index}" d="${pathForBrainEdge(from, to)}" stroke-width="${width}"></path>
    `;
  }).join("");
  const highlightedPropertyIds = visibleBrainLabelIds(positioned);
  const nodeMarkup = positioned.map((node) => {
    const radius = node.r || brainRadius(node);
    const label = String(node.label || "").length > 24 ? String(node.label).slice(0, 22) + "..." : String(node.label || "");
    const meta = node.type === "property" && node.score ? `${node.score} ${node.grade || ""}` : node.type;
    const labelClass = shouldShowBrainLabel(node, highlightedPropertyIds) ? " label-visible" : "";
    const selectedClass = state.brain.selectedNodeId === node.id ? " selected" : "";
    return `
      <g class="brain-node ${node.type}${labelClass}${selectedClass}" data-graph-node="${escapeHtml(node.id)}" transform="translate(${node.x}, ${node.y})"${node.property_id ? ` data-property="${escapeHtml(node.property_id)}"` : ""}>
        <title>${escapeHtml(node.label || node.id)}</title>
        <circle r="${radius}"></circle>
        <text class="brain-label" x="0" y="${radius + 18}" text-anchor="middle">${escapeHtml(label)}</text>
        <text class="brain-meta" x="0" y="${radius + 34}" text-anchor="middle">${escapeHtml(meta)}</text>
      </g>
    `;
  }).join("");
  svg.innerHTML = `<g id="brainViewport"><g class="brain-edges">${edgeMarkup}</g><g class="brain-nodes">${nodeMarkup}</g></g>`;
  graphSession.svg = svg;
  graphSession.viewport = svg.querySelector("#brainViewport");
  bindBrainInteractions(svg);
  applyBrainTransform();
  svg.querySelectorAll(".brain-node").forEach(bindBrainNodeDrag);
  updateBrainMoveControls();
}

function bindDynamicClicks() {
  document.querySelectorAll("[data-property]:not([data-property='']):not(.brain-node)").forEach((node) => {
    node.addEventListener("click", () => {
      state.selectedId = node.dataset.property;
      setView("property");
    });
  });
  document.querySelectorAll("[data-partner]").forEach((node) => {
    node.addEventListener("click", () => {
      state.partnerId = node.dataset.partner || "all";
      const partnerLens = accessLenses().find((lens) => lens.key === "partner_renovator");
      if (partnerLens && state.partnerId !== "all") state.accessLens = partnerLens.key;
      state.brain.signature = "";
      render();
    });
  });
}

function render() {
  const properties = filteredProperties();
  if (!properties.some((property) => property.id === state.selectedId)) {
    state.selectedId = properties[0]?.id || "";
  }
  renderPartnerControls();
  renderAccessLensControls();
  renderAccessLensPanel(properties);
  renderNetworkPanel(properties);
  renderExecutive(properties);
  renderTrust(properties);
  renderIntelligence(properties);
  renderMetrics(properties);
  renderModuleBars(properties);
  renderPriority(properties);
  renderTable(properties);
  renderPropertyProfile();
  renderMap(properties);
  renderCampaign(properties);
  renderBrain(properties);
  bindDynamicClicks();
}

function exportCsv() {
  const rows = filteredProperties().map((property) => {
    const best = bestAssessment(property);
    return [
      property.address,
      property.city,
      propertyPartnerName(property),
      property.territory || propertyPartner(property).region || "",
      best.key,
      best.score,
      best.grade,
      property.status,
      property.nextAction,
      propertyValue(property),
      estimatedFacadeM2(property)
    ];
  });
  const header = ["address", "city", "partner", "territory", "best_module", "best_score", "grade", "status", "next_action", "estimated_value", "estimated_facade_m2"];
  const csv = [header, ...rows].map((row) => row.map((cell) => `"${String(cell).replaceAll('"', '""')}"`).join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "homepilot_properties.csv";
  link.click();
  URL.revokeObjectURL(url);
}

document.querySelectorAll(".nav-tab").forEach((button) => {
  button.addEventListener("click", () => setView(button.dataset.view));
});

renderTenantControls();
renderModuleControls();
renderPartnerControls();
renderAccessLensControls();

document.getElementById("searchInput").addEventListener("input", (event) => {
  state.search = event.target.value;
  render();
});

document.getElementById("gradeFilter").addEventListener("change", (event) => {
  state.grade = event.target.value;
  render();
});

document.getElementById("statusFilter").addEventListener("change", (event) => {
  state.status = event.target.value;
  render();
});

document.getElementById("partnerSelect").addEventListener("change", (event) => {
  state.partnerId = event.target.value;
  const nextLensKey = state.partnerId === "all" ? "producer_network" : "partner_renovator";
  if (accessLenses().some((lens) => lens.key === nextLensKey)) state.accessLens = nextLensKey;
  state.brain.signature = "";
  render();
});

document.getElementById("accessLensSelect").addEventListener("change", (event) => {
  applyAccessLens(event.target.value);
  render();
});

document.getElementById("exportBtn").addEventListener("click", exportCsv);
document.getElementById("brainZoomOut").addEventListener("click", () => setBrainZoom(state.brain.scale * 0.82));
document.getElementById("brainZoomIn").addEventListener("click", () => setBrainZoom(state.brain.scale * 1.18));
document.getElementById("brainFit").addEventListener("click", () => fitBrainToViewport());
document.getElementById("brainResetLayout").addEventListener("click", () => {
  state.brain.pinned = {};
  state.brain.selectedNodeId = "";
  state.brain.signature = "";
  state.brain.layout = null;
  render();
});
document.getElementById("brainMoveMode").addEventListener("click", () => {
  state.brain.moveMode = !state.brain.moveMode;
  if (!state.brain.moveMode) state.brain.selectedNodeId = "";
  updateBrainSelectionDom();
});
document.getElementById("brainNudgeLeft").addEventListener("click", () => nudgeSelectedBrainNode(-28, 0));
document.getElementById("brainNudgeRight").addEventListener("click", () => nudgeSelectedBrainNode(28, 0));
document.getElementById("brainNudgeUp").addEventListener("click", () => nudgeSelectedBrainNode(0, -28));
document.getElementById("brainNudgeDown").addEventListener("click", () => nudgeSelectedBrainNode(0, 28));
document.getElementById("focusBestBtn").addEventListener("click", () => {
  state.grade = "A+";
  document.getElementById("gradeFilter").value = "A+";
  render();
});

if (window.HOMEPILOT_LIVE_SNAPSHOT) {
  applyDashboardData(window.HOMEPILOT_LIVE_SNAPSHOT);
} else {
  render();
}
