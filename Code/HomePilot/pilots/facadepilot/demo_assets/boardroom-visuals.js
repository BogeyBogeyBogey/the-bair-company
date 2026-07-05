(function () {
  const data = window.HOMEPILOT_DASHBOARD || { properties: [], campaigns: [] };
  const properties = (data.properties || []).filter((property) => (
    Number.isFinite(Number(property.lat)) && Number.isFinite(Number(property.lon))
  ));
  const byId = Object.fromEntries(properties.map((property) => [property.id, property]));
  const CONTACTED = new Set(["sent", "clicked", "responded", "appointment", "no_response"]);
  const ENGAGED = new Set(["clicked", "responded", "appointment"]);
  const MAP_WORLD = { width: 1880, height: 1120, pad: 115 };
  const BRAIN_WORLD = { width: 1660, height: 980 };

  const mapState = { scale: 1, tx: 0, ty: 0, topOnly: false, selectedId: "" };
  const brainState = {
    scale: 1,
    tx: 0,
    ty: 0,
    selectedId: "producer:daw",
    search: "",
    nodes: [],
    edges: [],
    byId: {}
  };

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      "\"": "&quot;",
      "'": "&#39;"
    }[char]));
  }

  function formatNumber(value, options = {}) {
    return new Intl.NumberFormat("nl-BE", options).format(Number(value) || 0);
  }

  function formatInteger(value) {
    return formatNumber(Math.round(Number(value) || 0), { maximumFractionDigits: 0 });
  }

  function formatMoney(value) {
    const amount = Number(value) || 0;
    if (amount >= 1000000) {
      return `EUR ${formatNumber(amount / 1000000, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}M`;
    }
    return `EUR ${formatInteger(amount)}`;
  }

  function formatPercent(value) {
    return `${formatInteger(value)}%`;
  }

  function bestAssessment(property) {
    const entries = Object.entries(property.assessments || {});
    if (!entries.length) return { key: "facadepilot", score: 0, grade: "", label: "No score", confidence: 0 };
    const [key, assessment] = entries.sort((a, b) => Number(b[1].score || 0) - Number(a[1].score || 0))[0];
    return { key, ...assessment };
  }

  function partnerOf(property) {
    return property.partner || {
      id: property.partner_id || "unknown",
      name: property.partner_name || "Partner",
      region: property.territory || property.city || ""
    };
  }

  function partnerName(property) {
    return partnerOf(property).name || "Partner";
  }

  function isTopProperty(property) {
    const best = bestAssessment(property);
    return ["A+", "A"].includes(best.grade) || Number(best.score || 0) >= 80;
  }

  function scoreLevel(score) {
    if (Number(score) >= 82) return "high";
    if (Number(score) >= 68) return "mid";
    return "low";
  }

  function mapBounds(list) {
    const lats = list.map((property) => Number(property.lat));
    const lons = list.map((property) => Number(property.lon));
    let minLat = Math.min(...lats);
    let maxLat = Math.max(...lats);
    let minLon = Math.min(...lons);
    let maxLon = Math.max(...lons);
    if (minLat === maxLat) {
      minLat -= 0.01;
      maxLat += 0.01;
    }
    if (minLon === maxLon) {
      minLon -= 0.01;
      maxLon += 0.01;
    }
    return { minLat, maxLat, minLon, maxLon };
  }

  function mapProject(property, bounds) {
    return {
      x: MAP_WORLD.pad + ((Number(property.lon) - bounds.minLon) / (bounds.maxLon - bounds.minLon)) * (MAP_WORLD.width - MAP_WORLD.pad * 2),
      y: MAP_WORLD.height - MAP_WORLD.pad - ((Number(property.lat) - bounds.minLat) / (bounds.maxLat - bounds.minLat)) * (MAP_WORLD.height - MAP_WORLD.pad * 2)
    };
  }

  function visibleMapProperties() {
    return mapState.topOnly ? properties.filter(isTopProperty) : properties;
  }

  function partnerSummaries(list, bounds) {
    const groups = {};
    list.forEach((property) => {
      const partner = partnerOf(property);
      const id = partner.id || partner.name || "partner";
      const pos = mapProject(property, bounds);
      const item = groups[id] || {
        id,
        name: partner.name || "Partner",
        region: partner.region || property.territory || "",
        x: 0,
        y: 0,
        count: 0,
        top: 0,
        value: 0
      };
      item.x += pos.x;
      item.y += pos.y;
      item.count += 1;
      item.top += isTopProperty(property) ? 1 : 0;
      item.value += Number(property.estimatedValue || 0);
      groups[id] = item;
    });
    return Object.values(groups).map((item) => ({
      ...item,
      x: item.x / Math.max(1, item.count),
      y: item.y / Math.max(1, item.count)
    }));
  }

  function clusterProperties(list, bounds, gridSize) {
    const clusters = {};
    list.forEach((property) => {
      const best = bestAssessment(property);
      const xIndex = Math.max(0, Math.min(gridSize - 1, Math.floor(((Number(property.lon) - bounds.minLon) / (bounds.maxLon - bounds.minLon)) * gridSize)));
      const yIndex = Math.max(0, Math.min(gridSize - 1, Math.floor(((Number(property.lat) - bounds.minLat) / (bounds.maxLat - bounds.minLat)) * gridSize)));
      const id = `${xIndex}:${yIndex}`;
      const cluster = clusters[id] || {
        id,
        lat: 0,
        lon: 0,
        count: 0,
        maxScore: 0,
        scoreSum: 0,
        value: 0,
        topPropertyId: property.id
      };
      cluster.lat += Number(property.lat);
      cluster.lon += Number(property.lon);
      cluster.count += 1;
      cluster.scoreSum += Number(best.score || 0);
      cluster.value += Number(property.estimatedValue || 0);
      if (Number(best.score || 0) >= cluster.maxScore) {
        cluster.maxScore = Number(best.score || 0);
        cluster.topPropertyId = property.id;
      }
      clusters[id] = cluster;
    });
    return Object.values(clusters).map((cluster) => ({
      ...cluster,
      lat: cluster.lat / cluster.count,
      lon: cluster.lon / cluster.count,
      avgScore: Math.round(cluster.scoreSum / cluster.count)
    })).sort((a, b) => b.count - a.count || b.maxScore - a.maxScore);
  }

  function applyMapTransform() {
    const world = document.getElementById("reportMapWorld");
    if (!world) return;
    world.style.transform = `translate(${mapState.tx}px, ${mapState.ty}px) scale(${mapState.scale})`;
  }

  function fitMap() {
    const viewport = document.getElementById("reportMapViewport");
    if (!viewport) return;
    const rect = viewport.getBoundingClientRect();
    const scale = Math.max(0.28, Math.min(1.2, Math.min(rect.width / MAP_WORLD.width, rect.height / MAP_WORLD.height) * 0.94));
    mapState.scale = scale;
    mapState.tx = (rect.width - MAP_WORLD.width * scale) / 2;
    mapState.ty = (rect.height - MAP_WORLD.height * scale) / 2;
    applyMapTransform();
  }

  function setMapZoom(nextScale, anchor) {
    const viewport = document.getElementById("reportMapViewport");
    if (!viewport) return;
    const rect = viewport.getBoundingClientRect();
    const point = anchor || { x: rect.width / 2, y: rect.height / 2 };
    const worldPoint = {
      x: (point.x - mapState.tx) / mapState.scale,
      y: (point.y - mapState.ty) / mapState.scale
    };
    mapState.scale = Math.max(0.24, Math.min(2.8, nextScale));
    mapState.tx = point.x - worldPoint.x * mapState.scale;
    mapState.ty = point.y - worldPoint.y * mapState.scale;
    applyMapTransform();
  }

  function selectMapProperty(propertyId) {
    const target = document.getElementById("reportMapInspector");
    const property = byId[propertyId];
    if (!target || !property) return;
    const best = bestAssessment(property);
    mapState.selectedId = propertyId;
    target.innerHTML = `
      <strong>${escapeHtml(property.address || property.id)}</strong>
      <span>${escapeHtml(property.city || "")} - ${escapeHtml(partnerName(property))}</span>
      <small>
        Score ${escapeHtml(best.score)} / ${escapeHtml(best.grade || "n/a")}<br>
        ${escapeHtml(best.label || "Facade opportunity")}<br>
        Status: ${escapeHtml(property.status || "queued")}<br>
        Pipeline: ${formatMoney(property.estimatedValue || 0)}<br>
        Next action: ${escapeHtml(property.nextAction || "Review with partner")}
      </small>
    `;
  }

  function renderMap() {
    const list = visibleMapProperties();
    const world = document.getElementById("reportMapWorld");
    const stats = document.getElementById("reportMapStats");
    if (!world || !stats || !list.length) return;

    const bounds = mapBounds(list);
    const partners = partnerSummaries(list, bounds);
    const clusters = clusterProperties(list, bounds, 11);
    const topPoints = list.slice().sort((a, b) => Number(bestAssessment(b).score || 0) - Number(bestAssessment(a).score || 0)).slice(0, 120);
    const contacted = list.filter((property) => CONTACTED.has(property.status)).length;
    const engaged = list.filter((property) => ENGAGED.has(property.status)).length;
    const topCount = list.filter(isTopProperty).length;
    const value = list.reduce((sum, property) => sum + Number(property.estimatedValue || 0), 0);

    stats.innerHTML = `
      <div><strong>${formatNumber(list.length)}</strong><span>Visible records</span></div>
      <div><strong>${formatNumber(topCount)}</strong><span>A/A+ focus</span></div>
      <div><strong>${formatNumber(partners.length)}</strong><span>Partners</span></div>
      <div><strong>${formatPercent((engaged / Math.max(1, contacted)) * 100)}</strong><span>Contacted response</span></div>
      <div><strong>${formatMoney(value)}</strong><span>Pipeline</span></div>
    `;

    const partnerMarkup = partners.map((partner) => `
      <div class="territory-label" style="left:${partner.x}px;top:${partner.y}px">
        <strong>${escapeHtml(partner.name)}</strong>
        <span>${formatNumber(partner.count)} records / ${formatNumber(partner.top)} A/A+</span>
      </div>
    `).join("");

    const clusterMarkup = clusters.map((cluster) => {
      const position = mapProject({ lat: cluster.lat, lon: cluster.lon }, bounds);
      const size = Math.max(38, Math.min(94, 31 + Math.sqrt(cluster.count) * 9));
      return `
        <button class="territory-cluster ${scoreLevel(cluster.maxScore)}" style="left:${position.x}px;top:${position.y}px;width:${size}px;height:${size}px" data-map-property="${escapeHtml(cluster.topPropertyId)}" type="button" aria-label="${cluster.count} records">
          <strong>${formatNumber(cluster.count)}</strong>
          <span>${cluster.maxScore}</span>
        </button>
      `;
    }).join("");

    const pointMarkup = topPoints.map((property) => {
      const position = mapProject(property, bounds);
      const best = bestAssessment(property);
      return `<button class="territory-point ${scoreLevel(best.score)}" style="left:${position.x}px;top:${position.y}px" data-map-property="${escapeHtml(property.id)}" type="button" title="${escapeHtml(property.address)}"></button>`;
    }).join("");

    world.innerHTML = `
      <div class="territory-grid"></div>
      <div class="territory-route one"></div>
      <div class="territory-route two"></div>
      ${partnerMarkup}
      ${clusterMarkup}
      ${pointMarkup}
    `;

    world.querySelectorAll("[data-map-property]").forEach((button) => {
      button.addEventListener("click", (event) => {
        event.stopPropagation();
        selectMapProperty(button.dataset.mapProperty);
      });
    });

    if (!mapState.selectedId && list[0]) selectMapProperty(list[0].id);
    document.getElementById("reportMapTop")?.classList.toggle("active", mapState.topOnly);
    fitMap();
  }

  function bindMapControls() {
    const viewport = document.getElementById("reportMapViewport");
    if (!viewport) return;
    let pan = null;
    viewport.addEventListener("wheel", (event) => {
      event.preventDefault();
      const rect = viewport.getBoundingClientRect();
      setMapZoom(mapState.scale * (event.deltaY > 0 ? 0.88 : 1.14), {
        x: event.clientX - rect.left,
        y: event.clientY - rect.top
      });
    }, { passive: false });
    viewport.addEventListener("pointerdown", (event) => {
      if (event.target.closest("[data-map-property]")) return;
      pan = { id: event.pointerId, x: event.clientX, y: event.clientY, tx: mapState.tx, ty: mapState.ty };
      viewport.setPointerCapture(event.pointerId);
      viewport.classList.add("is-panning");
    });
    viewport.addEventListener("pointermove", (event) => {
      if (!pan || pan.id !== event.pointerId) return;
      mapState.tx = pan.tx + event.clientX - pan.x;
      mapState.ty = pan.ty + event.clientY - pan.y;
      applyMapTransform();
    });
    const stop = (event) => {
      if (!pan || pan.id !== event.pointerId) return;
      pan = null;
      viewport.classList.remove("is-panning");
    };
    viewport.addEventListener("pointerup", stop);
    viewport.addEventListener("pointercancel", stop);

    document.getElementById("reportMapZoomOut")?.addEventListener("click", () => setMapZoom(mapState.scale * 0.82));
    document.getElementById("reportMapZoomIn")?.addEventListener("click", () => setMapZoom(mapState.scale * 1.18));
    document.getElementById("reportMapFit")?.addEventListener("click", fitMap);
    document.getElementById("reportMapTop")?.addEventListener("click", () => {
      mapState.topOnly = !mapState.topOnly;
      mapState.selectedId = "";
      renderMap();
    });
  }

  function groupByPartner() {
    const groups = {};
    properties.forEach((property) => {
      const partner = partnerOf(property);
      const id = partner.id || partner.name || "partner";
      const item = groups[id] || {
        id,
        name: partner.name || "Partner",
        region: partner.region || property.territory || "",
        properties: []
      };
      item.properties.push(property);
      groups[id] = item;
    });
    return Object.values(groups).sort((a, b) => a.name.localeCompare(b.name));
  }

  function buildBrain() {
    const nodes = [];
    const edges = [];
    const nodeIds = new Set();
    const edgeIds = new Set();
    const addNode = (node) => {
      if (!node || !node.id || nodeIds.has(node.id)) return;
      nodeIds.add(node.id);
      nodes.push(node);
    };
    const addEdge = (source, target, type, label, weight = 1) => {
      if (!source || !target || source === target) return;
      const id = `${source}>${target}:${type || "link"}`;
      if (edgeIds.has(id)) return;
      edgeIds.add(id);
      edges.push({ source, target, type, label, weight });
    };
    const cx = BRAIN_WORLD.width / 2;
    const cy = BRAIN_WORLD.height / 2;
    const topProperties = properties.filter(isTopProperty);
    const contacted = properties.filter((property) => CONTACTED.has(property.status)).length;
    const engaged = properties.filter((property) => ENGAGED.has(property.status)).length;
    const noResponse = properties.filter((property) => property.status === "no_response").length;
    const totalValue = properties.reduce((sum, property) => sum + Number(property.estimatedValue || 0), 0);
    const facadeM2 = properties.reduce((sum, property) => sum + Number(property.estimatedFacadeM2 || 0), 0);

    addNode({
      id: "producer:daw",
      type: "producer",
      label: "DAW Belgium",
      x: cx,
      y: cy,
      r: 48,
      detail: "Producer command node: aggregate view over partners, scoring signals, response proof and legal-first guardrails.",
      meta: `${formatNumber(properties.length)} records`,
      metrics: [
        `${formatNumber(topProperties.length)} A/A+ opportunities`,
        `${formatMoney(totalValue)} visible pipeline`,
        `${formatNumber(facadeM2)} m² facade context`
      ]
    });
    addNode({
      id: "module:facadepilot",
      type: "module",
      label: "FacadePilot",
      x: cx - 190,
      y: cy - 138,
      r: 34,
      detail: "Opportunity model for facade renovation campaigns, not homeowner intent profiling.",
      meta: "legal-first module",
      metrics: ["scores property opportunity", "keeps launch approval gated"]
    });
    addNode({
      id: "action:launch_gate",
      type: "action",
      label: "Launch gate",
      x: cx + 195,
      y: cy - 138,
      r: 32,
      detail: "Boardroom decision: approve scoped first wave only after customer go/no-go, suppression and routing proof.",
      meta: "proof gated",
      metrics: ["approval before outreach", "no live send from demo data"]
    });
    addNode({
      id: "action:field_photo",
      type: "action",
      label: "Field-photo audit",
      x: cx + 205,
      y: cy + 142,
      r: 29,
      detail: "Production visual proof should come from own capture, partner upload, licensed provider or official embed.",
      meta: "visual proof",
      metrics: ["shortlist before photography", "no Google-derived imagery"]
    });
    addNode({
      id: "status:response_loop",
      type: "status",
      label: "Response loop",
      x: cx - 205,
      y: cy + 142,
      r: 28,
      detail: "Only real replies, clicks and appointments become campaign learning evidence.",
      meta: `${formatPercent((engaged / Math.max(1, contacted)) * 100)} contacted response`,
      metrics: [`${formatNumber(engaged)} engaged records`, `${formatNumber(contacted)} contacted denominator`]
    });
    addEdge("producer:daw", "module:facadepilot", "module", "uses", 3);
    addEdge("producer:daw", "action:launch_gate", "action", "approve", 2.6);
    addEdge("producer:daw", "action:field_photo", "action", "verify", 2.2);
    addEdge("producer:daw", "status:response_loop", "status", "learns", 2.2);
    addEdge("module:facadepilot", "action:launch_gate", "action", "gates", 1.8);
    addEdge("status:response_loop", "action:launch_gate", "status", "proof", 1.4);

    const signalNodes = [
      { id: "signal:a_plus", label: "A/A+ queue", x: 245, y: 205, detail: "High-score property opportunity queue for first-wave review.", meta: `${formatNumber(topProperties.length)} records` },
      { id: "signal:surface", label: "Facade surface", x: 255, y: 492, detail: "Estimated facade surface supports pipeline sizing, not homeowner intent.", meta: `${formatNumber(facadeM2)} m²` },
      { id: "signal:public_context", label: "Public context", x: 255, y: 775, detail: "Source-backed context lane: licences, allowed use and provenance before production import.", meta: "source gated" },
      { id: "signal:retarget", label: "Retarget backlog", x: 1405, y: 775, detail: "No-response records are a follow-up queue, not negative intent.", meta: `${formatNumber(noResponse)} records` },
      { id: "signal:partner_fit", label: "Partner fit", x: 1405, y: 205, detail: "Routes opportunities to the right renovation partner before partner-level handoff.", meta: "scope safe" }
    ];
    signalNodes.forEach((node) => addNode({ ...node, type: "signal", r: 26 }));
    signalNodes.forEach((node) => addEdge("module:facadepilot", node.id, "signal", node.label, 2));

    const partners = groupByPartner();
    partners.forEach((partner, index) => {
      const angle = -Math.PI / 2 + (index / Math.max(1, partners.length)) * Math.PI * 2;
      const partnerId = `partner:${partner.id}`;
      const px = cx + Math.cos(angle) * 530;
      const py = cy + Math.sin(angle) * 335;
      const top = partner.properties.filter(isTopProperty).length;
      const engagedRows = partner.properties.filter((property) => ENGAGED.has(property.status));
      const response = engagedRows.length;
      const partnerNoResponse = partner.properties.filter((property) => property.status === "no_response").length;
      const partnerValue = partner.properties.reduce((sum, property) => sum + Number(property.estimatedValue || 0), 0);
      const avgScore = Math.round(partner.properties.reduce((sum, property) => sum + Number(bestAssessment(property).score || 0), 0) / Math.max(1, partner.properties.length));
      addNode({
        id: partnerId,
        type: "partner",
        label: partner.name,
        x: px,
        y: py,
        r: Math.max(28, Math.min(39, 25 + Math.sqrt(partner.properties.length))),
        detail: `${partner.region || "Region"} partner scope: ${formatNumber(partner.properties.length)} assigned records, ${formatNumber(top)} A/A+, ${formatNumber(response)} engaged.`,
        meta: `${formatNumber(top)} A/A+`,
        metrics: [`Avg score ${formatNumber(avgScore)}`, formatMoney(partnerValue), `${formatNumber(partnerNoResponse)} no-response`]
      });
      addEdge("producer:daw", partnerId, "partner", "partner scope", 2.6);
      addEdge(partnerId, "signal:partner_fit", "signal", "fit", 1.6);

      const partnerTop = partner.properties
        .slice()
        .sort((a, b) => Number(bestAssessment(b).score || 0) - Number(bestAssessment(a).score || 0))
        .slice(0, 3);
      const clusterRows = [
        {
          id: `cluster:${partner.id}:top`,
          label: `${formatNumber(top)} A/A+`,
          type: "cluster",
          count: top,
          x: px + Math.cos(angle - 0.18) * 108,
          y: py + Math.sin(angle - 0.18) * 108,
          target: "signal:a_plus",
          edge: "signal",
          meta: "review first",
          detail: `${partner.name}: first-wave shortlist with ${formatNumber(top)} A/A+ property opportunities.`,
          metrics: ["Approve shortlist before outreach", "Property opportunity, not homeowner intent"]
        },
        {
          id: `cluster:${partner.id}:response`,
          label: `${formatNumber(response)} engaged`,
          type: "cluster",
          count: response,
          x: px + Math.cos(angle + 0.12) * 152,
          y: py + Math.sin(angle + 0.12) * 152,
          target: "status:response_loop",
          edge: "status",
          meta: "proof loop",
          detail: `${partner.name}: clicked/responded/appointment rows become response learning once real campaign data exists.`,
          metrics: [`${formatNumber(response)} engaged demo records`, "Denominator stays contacted records"]
        },
        {
          id: `cluster:${partner.id}:retarget`,
          label: `${formatNumber(partnerNoResponse)} retarget`,
          type: "cluster",
          count: partnerNoResponse,
          x: px + Math.cos(angle + 0.34) * 122,
          y: py + Math.sin(angle + 0.34) * 122,
          target: "signal:retarget",
          edge: "action",
          meta: "follow-up",
          detail: `${partner.name}: no-response backlog can be reviewed for a lower-friction second message.`,
          metrics: [`${formatNumber(partnerNoResponse)} no-response`, "Retarget only after approval"]
        }
      ].filter((cluster) => cluster.count > 0);

      clusterRows.forEach((cluster) => {
        addNode({
          ...cluster,
          r: Math.max(18, Math.min(32, 15 + Math.sqrt(cluster.count) * 1.3))
        });
        addEdge(partnerId, cluster.id, "assignment", cluster.meta, 1.8);
        addEdge(cluster.id, cluster.target, cluster.edge, cluster.meta, 1.4);
      });

      partnerTop.forEach((property, propertyIndex) => {
        const cluster = clusterRows[0];
        if (!cluster) return;
        const spoke = angle + ((propertyIndex - 1) * 0.18);
        const distance = 54 + propertyIndex * 18;
        const best = bestAssessment(property);
        const propertyId = `property:${property.id}`;
        addNode({
          id: propertyId,
          type: "property",
          label: `${property.city || "Property"} ${best.score}`,
          x: cluster.x + Math.cos(spoke) * distance,
          y: cluster.y + Math.sin(spoke) * distance,
          r: Math.max(8, Math.min(15, Number(best.score || 0) / 7)),
          propertyId: property.id,
          score: best.score,
          meta: best.grade || "",
          detail: `${property.address} - ${best.label || "Facade signal"} - ${property.status || "queued"}`,
          metrics: [formatMoney(property.estimatedValue || 0), `${formatNumber(property.estimatedFacadeM2 || 0)} m² facade`]
        });
        addEdge(cluster.id, propertyId, "assignment", "sample", 1);
        addEdge(propertyId, "signal:surface", "signal", "value", 1);
      });
    });

    brainState.nodes = nodes;
    brainState.edges = edges;
    brainState.byId = Object.fromEntries(nodes.map((node) => [node.id, node]));
  }

  function edgePath(edge) {
    const source = brainState.byId[edge.source];
    const target = brainState.byId[edge.target];
    if (!source || !target) return "";
    const dx = target.x - source.x;
    const dy = target.y - source.y;
    const curve = Math.min(120, Math.max(28, Math.hypot(dx, dy) * 0.18));
    return `M ${source.x} ${source.y} C ${source.x + curve} ${source.y + dy * 0.12}, ${target.x - curve} ${target.y - dy * 0.12}, ${target.x} ${target.y}`;
  }

  function nodeSearchText(node) {
    return [
      node.id,
      node.label,
      node.type,
      node.detail,
      node.meta,
      node.score,
      ...(node.metrics || [])
    ].filter(Boolean).join(" ").toLowerCase();
  }

  function matchesSearch(node) {
    const query = brainState.search.trim().toLowerCase();
    return !query || nodeSearchText(node).includes(query);
  }

  function applyBrainTransform() {
    const layer = document.getElementById("reportBrainLayer");
    if (layer) layer.setAttribute("transform", `translate(${brainState.tx} ${brainState.ty}) scale(${brainState.scale})`);
  }

  function renderBrainInspector() {
    const target = document.getElementById("reportBrainInspector");
    if (!target) return;
    const node = brainState.byId[brainState.selectedId];
    if (!node) {
      const matched = brainState.nodes.filter(matchesSearch).length;
      target.innerHTML = `<strong>${matched} matching nodes</strong><span>Search or click a node.</span><small>Drag the empty graph background to pan. Scroll to zoom.</small>`;
      return;
    }
    const links = brainState.edges
      .filter((edge) => edge.source === node.id || edge.target === node.id)
      .slice(0, 6)
      .map((edge) => {
        const otherId = edge.source === node.id ? edge.target : edge.source;
        const other = brainState.byId[otherId];
        return `${edge.label || edge.type}: ${other?.label || otherId}`;
      });
    const metrics = (node.metrics || []).slice(0, 4).map((item) => `<span>${escapeHtml(item)}</span>`).join("");
    target.innerHTML = `
      <strong>${escapeHtml(node.label)}</strong>
      <span>${escapeHtml(node.type)}${node.meta ? ` - ${escapeHtml(node.meta)}` : ""}${node.score ? ` - score ${escapeHtml(node.score)}` : ""}</span>
      <small>${escapeHtml(node.detail || "Graph context")}</small>
      ${metrics ? `<div class="inspector-metrics">${metrics}</div>` : ""}
      <small>${links.map(escapeHtml).join("<br>")}</small>
    `;
  }

  function renderBrainInsights() {
    const target = document.getElementById("reportBrainInsights");
    if (!target) return;
    const top = properties.filter(isTopProperty).length;
    const partners = groupByPartner().length;
    const contacted = properties.filter((property) => CONTACTED.has(property.status)).length;
    const engaged = properties.filter((property) => ENGAGED.has(property.status)).length;
    const noResponse = properties.filter((property) => property.status === "no_response").length;
    target.innerHTML = [
      ["Reusable memory", `${formatNumber(brainState.nodes.length)} nodes`, "partners, signals, actions and proof loops"],
      ["First-wave focus", `${formatNumber(top)} A/A+`, "shortlist before field-photo spend"],
      ["Partner network", `${formatNumber(partners)} scopes`, "each partner keeps assigned records only"],
      ["Learning loop", formatPercent((engaged / Math.max(1, contacted)) * 100), `${formatNumber(noResponse)} retarget candidates`]
    ].map(([label, value, detail]) => `
      <div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(detail)}</small></div>
    `).join("");
  }

  function renderBrainLegend() {
    const target = document.getElementById("reportBrainLegend");
    if (!target) return;
    target.innerHTML = [
      ["module", "FacadePilot module"],
      ["partner", "Renovation partner"],
      ["cluster", "Opportunity cluster"],
      ["signal", "Scoring signal"],
      ["status", "Response loop"],
      ["action", "Next action"]
    ].map(([type, label]) => `<span><i class="${type}"></i>${escapeHtml(label)}</span>`).join("");
  }

  function renderBrain() {
    const svg = document.getElementById("reportBrainGraph");
    if (!svg) return;
    const selected = brainState.selectedId;
    const focusActive = Boolean(selected && selected !== "producer:daw");
    const connected = new Set(selected ? [selected] : []);
    brainState.edges.forEach((edge) => {
      if (edge.source === selected) connected.add(edge.target);
      if (edge.target === selected) connected.add(edge.source);
    });
    const edgeMarkup = brainState.edges.map((edge, index) => {
      const isSelected = edge.source === selected || edge.target === selected;
      const dimmed = focusActive && !isSelected ? " dimmed" : "";
      const width = Math.max(1.2, Math.min(4.6, Number(edge.weight || 1.2)));
      return `<path class="brain-edge ${edge.type || "link"}${isSelected ? " selected" : ""}${dimmed}" data-edge-index="${index}" d="${edgePath(edge)}" stroke-width="${width}"></path>`;
    }).join("");
    const hasSearch = Boolean(brainState.search.trim());
    const nodeMarkup = brainState.nodes.map((node) => {
      const selectedClass = node.id === selected ? " selected" : "";
      const linkedClass = selected && connected.has(node.id) && node.id !== selected ? " linked" : "";
      const dimmedClass = focusActive && !connected.has(node.id) ? " dimmed" : "";
      const searchClass = brainState.search ? (matchesSearch(node) ? " search-match" : " search-muted") : "";
      const showLabel = !["property"].includes(node.type) || node.id === selected || (hasSearch && matchesSearch(node));
      const label = String(node.label || node.id).length > 24 ? `${String(node.label || node.id).slice(0, 22)}...` : String(node.label || node.id);
      const meta = node.meta || (node.score ? `score ${node.score}` : node.type);
      const metaY = (node.r || 12) + 34;
      return `
        <g class="brain-node ${node.type}${selectedClass}${linkedClass}${dimmedClass}${searchClass}" data-brain-node="${escapeHtml(node.id)}" transform="translate(${node.x} ${node.y})">
          <title>${escapeHtml(node.detail || node.label)}</title>
          <circle r="${node.r || 12}"></circle>
          ${showLabel ? `<text x="0" y="${(node.r || 12) + 18}" text-anchor="middle">${escapeHtml(label)}</text>` : ""}
          ${showLabel && meta ? `<text class="brain-meta" x="0" y="${metaY}" text-anchor="middle">${escapeHtml(meta)}</text>` : ""}
        </g>
      `;
    }).join("");
    const backdrop = `
      <defs>
        <filter id="reportBrainGlow" x="-80%" y="-80%" width="260%" height="260%">
          <feGaussianBlur stdDeviation="5" result="blur"></feGaussianBlur>
          <feMerge><feMergeNode in="blur"></feMergeNode><feMergeNode in="SourceGraphic"></feMergeNode></feMerge>
        </filter>
      </defs>
      <g class="brain-backdrop">
        <circle class="brain-ring ring-outer" cx="590" cy="345" r="296"></circle>
        <circle class="brain-ring ring-mid" cx="590" cy="345" r="206"></circle>
        <circle class="brain-ring ring-core" cx="590" cy="345" r="98"></circle>
        <path class="brain-axis" d="M118 345 H1062"></path>
        <path class="brain-axis" d="M590 64 V626"></path>
      </g>
    `;
    svg.innerHTML = `${backdrop}<g id="reportBrainLayer"><g class="brain-edges">${edgeMarkup}</g><g class="brain-nodes">${nodeMarkup}</g></g>`;
    applyBrainTransform();
    svg.querySelectorAll("[data-brain-node]").forEach(bindBrainNode);
    renderBrainInsights();
    renderBrainLegend();
    renderBrainInspector();
  }

  function svgPoint(event) {
    const svg = document.getElementById("reportBrainGraph");
    const rect = svg.getBoundingClientRect();
    return {
      x: ((event.clientX - rect.left) / Math.max(1, rect.width)) * 1180,
      y: ((event.clientY - rect.top) / Math.max(1, rect.height)) * 690
    };
  }

  function worldPoint(event) {
    const point = svgPoint(event);
    return {
      x: (point.x - brainState.tx) / brainState.scale,
      y: (point.y - brainState.ty) / brainState.scale
    };
  }

  function updateBrainPositions() {
    document.querySelectorAll("[data-edge-index]").forEach((path) => {
      const edge = brainState.edges[Number(path.dataset.edgeIndex)];
      path.setAttribute("d", edgePath(edge));
    });
    document.querySelectorAll("[data-brain-node]").forEach((group) => {
      const node = brainState.byId[group.dataset.brainNode];
      if (node) group.setAttribute("transform", `translate(${node.x} ${node.y})`);
    });
  }

  function bindBrainNode(group) {
    let drag = null;
    group.addEventListener("pointerdown", (event) => {
      event.stopPropagation();
      const node = brainState.byId[group.dataset.brainNode];
      if (!node) return;
      const start = worldPoint(event);
      drag = { id: event.pointerId, start, x: node.x, y: node.y, moved: false };
      group.setPointerCapture(event.pointerId);
      brainState.selectedId = node.id;
      renderBrainInspector();
    });
    group.addEventListener("pointermove", (event) => {
      if (!drag || drag.id !== event.pointerId) return;
      const point = worldPoint(event);
      const dx = point.x - drag.start.x;
      const dy = point.y - drag.start.y;
      if (Math.hypot(dx, dy) > 3) drag.moved = true;
      const node = brainState.byId[group.dataset.brainNode];
      if (!node) return;
      node.x = Math.max(40, Math.min(BRAIN_WORLD.width - 40, drag.x + dx));
      node.y = Math.max(40, Math.min(BRAIN_WORLD.height - 40, drag.y + dy));
      updateBrainPositions();
    });
    const stop = (event) => {
      if (!drag || drag.id !== event.pointerId) return;
      drag = null;
      renderBrainInspector();
    };
    group.addEventListener("pointerup", stop);
    group.addEventListener("pointercancel", stop);
    group.addEventListener("click", (event) => {
      event.stopPropagation();
      brainState.selectedId = group.dataset.brainNode;
      renderBrain();
    });
  }

  function fitBrain() {
    const svg = document.getElementById("reportBrainGraph");
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const scale = Math.max(0.35, Math.min(1.15, Math.min(1180 / BRAIN_WORLD.width, 690 / BRAIN_WORLD.height, rect.width / BRAIN_WORLD.width * 1.05)));
    brainState.scale = scale;
    brainState.tx = (1180 - BRAIN_WORLD.width * scale) / 2;
    brainState.ty = (690 - BRAIN_WORLD.height * scale) / 2;
    applyBrainTransform();
  }

  function setBrainZoom(nextScale, anchor) {
    const point = anchor || { x: 590, y: 345 };
    const world = {
      x: (point.x - brainState.tx) / brainState.scale,
      y: (point.y - brainState.ty) / brainState.scale
    };
    brainState.scale = Math.max(0.28, Math.min(2.7, nextScale));
    brainState.tx = point.x - world.x * brainState.scale;
    brainState.ty = point.y - world.y * brainState.scale;
    applyBrainTransform();
  }

  function bindBrainControls() {
    const svg = document.getElementById("reportBrainGraph");
    if (!svg) return;
    let pan = null;
    svg.addEventListener("wheel", (event) => {
      event.preventDefault();
      setBrainZoom(brainState.scale * (event.deltaY > 0 ? 0.88 : 1.14), svgPoint(event));
    }, { passive: false });
    svg.addEventListener("pointerdown", (event) => {
      if (event.target.closest("[data-brain-node]")) return;
      const start = svgPoint(event);
      pan = { id: event.pointerId, start, tx: brainState.tx, ty: brainState.ty };
      svg.setPointerCapture(event.pointerId);
      svg.classList.add("is-panning");
    });
    svg.addEventListener("pointermove", (event) => {
      if (!pan || pan.id !== event.pointerId) return;
      const point = svgPoint(event);
      brainState.tx = pan.tx + point.x - pan.start.x;
      brainState.ty = pan.ty + point.y - pan.start.y;
      applyBrainTransform();
    });
    const stop = (event) => {
      if (!pan || pan.id !== event.pointerId) return;
      pan = null;
      svg.classList.remove("is-panning");
    };
    svg.addEventListener("pointerup", stop);
    svg.addEventListener("pointercancel", stop);

    document.getElementById("reportBrainZoomOut")?.addEventListener("click", () => setBrainZoom(brainState.scale * 0.82));
    document.getElementById("reportBrainZoomIn")?.addEventListener("click", () => setBrainZoom(brainState.scale * 1.18));
    document.getElementById("reportBrainFit")?.addEventListener("click", fitBrain);
    document.getElementById("reportBrainSearch")?.addEventListener("input", (event) => {
      brainState.search = event.target.value || "";
      renderBrain();
    });
  }

  function init() {
    if (!properties.length) return;
    bindMapControls();
    renderMap();
    buildBrain();
    bindBrainControls();
    renderBrain();
    fitBrain();
    window.addEventListener("resize", () => {
      fitMap();
      fitBrain();
    });
  }

  init();
}());
