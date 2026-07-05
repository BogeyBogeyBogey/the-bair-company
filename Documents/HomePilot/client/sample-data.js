window.HOMEPILOT_SAMPLE = {
  tenant: {
    id: "homepilot-demo",
    name: "HomePilot demo",
    modules: ["facadepilot", "windowpilot", "roofpilot", "drivewaypilot"]
  },
  campaigns: [
    { id: "facade-leuven-q3", name: "Facade Leuven Q3", module: "facadepilot" },
    { id: "windows-ring-east", name: "Windows Ring East", module: "windowpilot" }
  ],
  properties: [
    {
      id: "prop_001",
      address: "Tiensesteenweg 56",
      city: "Bunsbeek",
      lat: 50.841,
      lon: 4.947,
      status: "responded",
      nextAction: "Call after 18:00",
      estimatedValue: 47000,
      tags: ["halfopen", "pre-1990 area", "energy story"],
      assessments: {
        facadepilot: { score: 86, grade: "A+", label: "Crepi + insulation", confidence: 0.88 },
        windowpilot: { score: 91, grade: "A+", label: "Old glazing signal", confidence: 0.81 },
        roofpilot: { score: 63, grade: "A", label: "Moss visible", confidence: 0.74 }
      },
      interactions: [
        { date: "2026-06-02", type: "flyer_sent", detail: "Facade concept sent" },
        { date: "2026-06-05", type: "scan", detail: "Landing page viewed twice" },
        { date: "2026-06-06", type: "form_submit", detail: "Asked about facade and windows" }
      ],
      objections: ["Timing after summer"]
    },
    {
      id: "prop_002",
      address: "Beekstraat 32",
      city: "Mechelen",
      lat: 51.026,
      lon: 4.477,
      status: "appointment",
      nextAction: "Prepare combined window and roof estimate",
      estimatedValue: 72000,
      tags: ["detached", "large envelope", "premium fit"],
      assessments: {
        facadepilot: { score: 79, grade: "A", label: "Total renovation", confidence: 0.83 },
        windowpilot: { score: 88, grade: "A+", label: "Frame replacement", confidence: 0.84 },
        roofpilot: { score: 82, grade: "A+", label: "Roof refresh", confidence: 0.79 },
        drivewaypilot: { score: 54, grade: "B", label: "Paving upsell", confidence: 0.62 }
      },
      interactions: [
        { date: "2026-06-01", type: "email_sent", detail: "WindowPilot visual sent" },
        { date: "2026-06-03", type: "call", detail: "Interested in financing options" },
        { date: "2026-06-10", type: "meeting", detail: "Site visit booked" }
      ],
      objections: ["Needs financing"]
    },
    {
      id: "prop_003",
      address: "Kerkstraat 18",
      city: "Tienen",
      lat: 50.809,
      lon: 4.937,
      status: "sent",
      nextAction: "Send softer facade message",
      estimatedValue: 28000,
      tags: ["rijwoning", "brick", "classic street"],
      assessments: {
        facadepilot: { score: 67, grade: "A", label: "Rejoint brick", confidence: 0.86 },
        windowpilot: { score: 59, grade: "B", label: "Mixed frames", confidence: 0.69 }
      },
      interactions: [
        { date: "2026-06-07", type: "flyer_sent", detail: "Brick restoration variant" }
      ],
      objections: []
    },
    {
      id: "prop_004",
      address: "Naamsesteenweg 144",
      city: "Leuven",
      lat: 50.873,
      lon: 4.701,
      status: "no_response",
      nextAction: "Retarget with energy savings copy",
      estimatedValue: 39000,
      tags: ["corner house", "visible side wall", "student area"],
      assessments: {
        facadepilot: { score: 74, grade: "A", label: "Insulated cladding", confidence: 0.77 },
        windowpilot: { score: 72, grade: "A", label: "Noise reduction story", confidence: 0.72 },
        roofpilot: { score: 48, grade: "B", label: "Low urgency", confidence: 0.58 }
      },
      interactions: [
        { date: "2026-06-04", type: "flyer_sent", detail: "No scan after 10 days" },
        { date: "2026-06-14", type: "status_change", detail: "Marked no response" }
      ],
      objections: ["No response"]
    },
    {
      id: "prop_005",
      address: "Stationsstraat 9",
      city: "Aarschot",
      lat: 50.987,
      lon: 4.836,
      status: "generated",
      nextAction: "Queue for direct mail",
      estimatedValue: 61000,
      tags: ["large detached", "driveway", "roof cross-sell"],
      assessments: {
        facadepilot: { score: 82, grade: "A+", label: "Premium facade", confidence: 0.8 },
        roofpilot: { score: 78, grade: "A", label: "Roof plus gutter", confidence: 0.73 },
        drivewaypilot: { score: 76, grade: "A", label: "Driveway renewal", confidence: 0.71 }
      },
      interactions: [],
      objections: []
    },
    {
      id: "prop_006",
      address: "Dorpstraat 41",
      city: "Lubbeek",
      lat: 50.882,
      lon: 4.84,
      status: "responded",
      nextAction: "Offer roof-first package",
      estimatedValue: 54000,
      tags: ["roof first", "older detached", "family home"],
      assessments: {
        facadepilot: { score: 58, grade: "B", label: "Facade later", confidence: 0.64 },
        windowpilot: { score: 66, grade: "A", label: "Thermal comfort", confidence: 0.7 },
        roofpilot: { score: 89, grade: "A+", label: "Roof priority", confidence: 0.86 }
      },
      interactions: [
        { date: "2026-06-08", type: "scan", detail: "Roof visual opened" },
        { date: "2026-06-09", type: "call", detail: "Asked for phased approach" }
      ],
      objections: ["Budget spread"]
    }
  ],
  recommendations: [
    "Combined window and facade messages outperform facade-only follow-up on high-income halfopen homes.",
    "Roof-first prospects respond better when the first call avoids aesthetic language and leads with energy loss.",
    "No-response properties near Leuven ring should be retargeted with quieter copy and a smaller renovation package.",
    "DrivewayPilot is strongest as an upsell after roof interest, not as the first campaign hook."
  ],
  trust: {
    sourceLedger: {
      report_type: "homepilot_source_ledger",
      status: "pass",
      review_status: "ready",
      scope: {
        tenant_scoped: true,
        module_keys: ["facadepilot", "windowpilot", "roofpilot", "drivewaypilot"]
      },
      summary: {
        properties: 6,
        assessments: 18,
        campaigns: 2,
        campaign_targets: 6,
        interactions: 10,
        evidence_references: 24,
        source_runs: 4,
        average_confidence: 0.77,
        contacted: 5,
        responses: 3,
        response_rate_pct: 60,
        latest_timestamp: "2026-06-14T00:00:00+00:00",
        timestamp_coverage_pct: 84,
        review_gap_count: 0
      },
      source_runs: [
        { source_run_id: "facade-leuven-q3-visual-scan", assessments: 5 },
        { source_run_id: "windows-ring-east-glazing-scan", assessments: 5 },
        { source_run_id: "roof-cross-sell-review", assessments: 5 },
        { source_run_id: "driveway-upsell-review", assessments: 3 }
      ],
      evidence_by_type: [
        { type: "streetview", count: 8 },
        { type: "aerial", count: 6 },
        { type: "render", count: 5 },
        { type: "campaign_response", count: 5 }
      ],
      module_coverage: [
        { module_key: "facadepilot", module_label: "FacadePilot", assessments: 6, evidence_references: 8, score_coverage_pct: 100, evidence_coverage_pct: 100, average_confidence: 0.79, response_rate_pct: 50 },
        { module_key: "windowpilot", module_label: "WindowPilot", assessments: 5, evidence_references: 7, score_coverage_pct: 100, evidence_coverage_pct: 100, average_confidence: 0.75, response_rate_pct: 66.67 },
        { module_key: "roofpilot", module_label: "RoofPilot", assessments: 5, evidence_references: 6, score_coverage_pct: 100, evidence_coverage_pct: 100, average_confidence: 0.74, response_rate_pct: 60 },
        { module_key: "drivewaypilot", module_label: "DrivewayPilot", assessments: 2, evidence_references: 3, score_coverage_pct: 100, evidence_coverage_pct: 100, average_confidence: 0.67, response_rate_pct: 0 }
      ],
      review_gaps: [],
      failures: [],
      guardrails: {
        source: "tenant/module-scoped HomePilot demo payload",
        tenant_scoped: true,
        raw_internal_fields_excluded: true,
        lead_claim_language_required: true,
        opportunity_not_intent_without_response: true,
        cross_customer_learning: "aggregate-only outside this customer package"
      }
    }
  },
  brain: {
    nodes: [
      { id: "tenant:bair", label: "Bair workspace", type: "tenant", weight: 6 },
      { id: "module:facadepilot", label: "Facade", type: "module", module_key: "facadepilot" },
      { id: "module:windowpilot", label: "Windows", type: "module", module_key: "windowpilot" },
      { id: "module:roofpilot", label: "Roof", type: "module", module_key: "roofpilot" },
      { id: "signal:energy_story", label: "Energy story", type: "signal" },
      { id: "signal:old_glazing", label: "Old glazing", type: "signal", module_key: "windowpilot" },
      { id: "property:prop_001", label: "Tiensesteenweg 56", type: "property", property_id: "prop_001", score: 91, grade: "A+", module_key: "windowpilot", status: "responded" },
      { id: "property:prop_002", label: "Beekstraat 32", type: "property", property_id: "prop_002", score: 88, grade: "A+", module_key: "windowpilot", status: "appointment" },
      { id: "reaction:responded", label: "Responded", type: "reaction", status: "responded" },
      { id: "objection:financing", label: "Needs financing", type: "objection" },
      { id: "action:call", label: "Call priority lead", type: "action" }
    ],
    edges: [
      { source: "tenant:bair", target: "module:windowpilot", type: "enabled_module", label: "enabled" },
      { source: "tenant:bair", target: "module:facadepilot", type: "enabled_module", label: "enabled" },
      { source: "module:windowpilot", target: "property:prop_001", type: "scores_property", label: "scores", module_key: "windowpilot", property_id: "prop_001", score: 91 },
      { source: "module:windowpilot", target: "property:prop_002", type: "scores_property", label: "scores", module_key: "windowpilot", property_id: "prop_002", score: 88 },
      { source: "signal:energy_story", target: "property:prop_001", type: "tag_signal", label: "signal", property_id: "prop_001" },
      { source: "signal:old_glazing", target: "property:prop_001", type: "assessment_signal", label: "evidence", module_key: "windowpilot", property_id: "prop_001" },
      { source: "property:prop_001", target: "reaction:responded", type: "campaign_status", label: "status", property_id: "prop_001" },
      { source: "property:prop_002", target: "objection:financing", type: "objection", label: "objection", property_id: "prop_002" },
      { source: "reaction:responded", target: "action:call", type: "next_action", label: "next", property_id: "prop_001" }
    ],
    stats: { nodes: 11, edges: 9, properties: 2, modules: 3, signals: 2, reactions: 2 }
  }
};
