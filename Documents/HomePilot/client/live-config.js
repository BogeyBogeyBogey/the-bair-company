window.HOMEPILOT_LIVE_CONFIG = window.HOMEPILOT_LIVE_CONFIG || {
  enabled: false,
  supabaseUrl: "",
  supabaseAnonKey: "",
  accessTokenStorageKey: "homepilot.customerJwt",
  tenant: { id: "", name: "", modules: [] },
  modules: [],
  views: {
    propertyIntelligence: "homepilot_property_intelligence",
    campaignMetrics: "homepilot_campaign_metrics",
    secondBrainEdges: "homepilot_second_brain_edges"
  }
};
