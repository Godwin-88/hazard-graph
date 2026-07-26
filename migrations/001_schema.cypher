// ============================================================
// HazardGraph — Full Neo4j Schema + Seed Data
// Migration 001
// Run: cypher-shell -a $NEO4J_URI -u $NEO4J_USER -p $NEO4J_PASSWORD < this_file
// ============================================================

// -----------------------------------------------------------
// 1. Constraints (uniqueness + existence)
// -----------------------------------------------------------
CREATE CONSTRAINT region_id IF NOT EXISTS FOR (r:Region) REQUIRE r.id IS UNIQUE;
CREATE CONSTRAINT hazard_type_id IF NOT EXISTS FOR (h:HazardType) REQUIRE h.id IS UNIQUE;
CREATE CONSTRAINT hazard_regime_id IF NOT EXISTS FOR (hr:HazardRegime) REQUIRE hr.id IS UNIQUE;
CREATE CONSTRAINT intervention_strategy_id IF NOT EXISTS FOR (is:InterventionStrategy) REQUIRE is.id IS UNIQUE;
CREATE CONSTRAINT forecast_signal_id IF NOT EXISTS FOR (fs:ForecastSignal) REQUIRE fs.id IS UNIQUE;
CREATE CONSTRAINT rainfall_signal_id IF NOT EXISTS FOR (rs:RainfallSignal) REQUIRE rs.id IS UNIQUE;
CREATE CONSTRAINT food_price_signal_id IF NOT EXISTS FOR (fps:FoodPriceSignal) REQUIRE fps.id IS UNIQUE;
CREATE CONSTRAINT ipc_phase_signal_id IF NOT EXISTS FOR (ipc:IPCPhaseSignal) REQUIRE ipc.id IS UNIQUE;
CREATE CONSTRAINT vulnerability_index_id IF NOT EXISTS FOR (vi:VulnerabilityIndex) REQUIRE vi.id IS UNIQUE;
CREATE CONSTRAINT stochastic_signal_id IF NOT EXISTS FOR (ss:StochasticSignal) REQUIRE ss.id IS UNIQUE;
CREATE CONSTRAINT ml_forecast_id IF NOT EXISTS FOR (mlf:MLForecast) REQUIRE mlf.id IS UNIQUE;
CREATE CONSTRAINT bma_score_id IF NOT EXISTS FOR (bma:BMAScore) REQUIRE bma.id IS UNIQUE;
CREATE CONSTRAINT causal_edge_id IF NOT EXISTS FOR (ce:CausalEdge) REQUIRE ce.id IS UNIQUE;
CREATE CONSTRAINT alert_id IF NOT EXISTS FOR (a:Alert) REQUIRE a.id IS UNIQUE;
CREATE CONSTRAINT data_source_id IF NOT EXISTS FOR (ds:DataSource) REQUIRE ds.id IS UNIQUE;
CREATE CONSTRAINT hazard_cluster_id IF NOT EXISTS FOR (hc:HazardCluster) REQUIRE hc.id IS UNIQUE;

// -----------------------------------------------------------
// 2. Indexes for frequent property lookups
// -----------------------------------------------------------
CREATE INDEX region_name IF NOT EXISTS FOR (r:Region) ON (r.name);
CREATE INDEX region_country IF NOT EXISTS FOR (r:Region) ON (r.country);
CREATE INDEX hazard_type_category IF NOT EXISTS FOR (h:HazardType) ON (h.category);
CREATE INDEX alert_status IF NOT EXISTS FOR (a:Alert) ON (a.status);
CREATE INDEX alert_region IF NOT EXISTS FOR (a:Alert) ON (a.region_id);
CREATE INDEX signal_created_at IF NOT EXISTS FOR (fs:ForecastSignal) ON (fs.created_at);
CREATE INDEX data_source_name IF NOT EXISTS FOR (ds:DataSource) ON (ds.name);
CREATE INDEX cluster_label IF NOT EXISTS FOR (hc:HazardCluster) ON (hc.label);

// -----------------------------------------------------------
// 3. Seed: Hazard Types (IGAD region relevant)
// -----------------------------------------------------------
MERGE (h1:HazardType {id: "hazard_drought"})
  SET h1.name = "Drought", h1.category = "hydroclimatic";
MERGE (h2:HazardType {id: "hazard_flood"})
  SET h2.name = "Flood", h2.category = "hydroclimatic";
MERGE (h3:HazardType {id: "hazard_locust"})
  SET h3.name = "Locust", h3.category = "biological";
MERGE (h4:HazardType {id: "hazard_conflict"})
  SET h4.name = "Conflict", h4.category = "sociopolitical";
MERGE (h5:HazardType {id: "hazard_heatwave"})
  SET h5.name = "Heatwave", h5.category = "hydroclimatic";
MERGE (h6:HazardType {id: "hazard_disease_outbreak"})
  SET h6.name = "Disease Outbreak", h6.category = "biological";
MERGE (h7:HazardType {id: "hazard_storm"})
  SET h7.name = "Storm", h7.category = "hydroclimatic";
MERGE (h8:HazardType {id: "hazard_landslide"})
  SET h8.name = "Landslide", h8.category = "geophysical";
MERGE (h9:HazardType {id: "hazard_frost"})
  SET h9.name = "Frost", h9.category = "hydroclimatic";
MERGE (h10:HazardType {id: "hazard_wildfire"})
  SET h10.name = "Wildfire", h10.category = "biological";
MERGE (h11:HazardType {id: "hazard_market_shock"})
  SET h11.name = "Market Shock", h11.category = "socioeconomic";

// -----------------------------------------------------------
// 4. Seed: Hazard Regimes (severity 0–4)
// -----------------------------------------------------------
MERGE (hr0:HazardRegime {id: "regime_baseline"})
  SET hr0.name = "Baseline", hr0.description = "Normal conditions, no elevated hazard risk", hr0.severity_level = 0;

MERGE (hr1:HazardRegime {id: "regime_drought_onset"})
  SET hr1.name = "Drought Onset", hr1.description = "Early-stage drought conditions developing", hr1.severity_level = 1;

MERGE (hr2:HazardRegime {id: "regime_severe_drought"})
  SET hr2.name = "Severe Drought", hr2.description = "Extended drought with severe impacts on livelihoods", hr2.severity_level = 3;

MERGE (hr3:HazardRegime {id: "regime_flood_watch"})
  SET hr3.name = "Flood Watch", hr3.description = "Elevated flood risk based on forecasts and rainfall", hr3.severity_level = 2;

MERGE (hr4:HazardRegime {id: "regime_flood_emergency"})
  SET hr4.name = "Flood Emergency", hr4.description = "Active flooding with humanitarian emergency", hr4.severity_level = 4;

// -----------------------------------------------------------
// 5. Seed: IGAD 11 Country Regions (admin-level-0)
// -----------------------------------------------------------
MERGE (r1:Region {id: "region_ethiopia"})
  SET r1.name = "Ethiopia", r1.country = "Ethiopia", r1.admin_level = 0,
      r1.current_risk_score = 0.0, r1.pagerank_score = 0.0, r1.current_regime = "regime_baseline";

MERGE (r2:Region {id: "region_kenya"})
  SET r2.name = "Kenya", r2.country = "Kenya", r2.admin_level = 0,
      r2.current_risk_score = 0.0, r2.pagerank_score = 0.0, r2.current_regime = "regime_baseline";

MERGE (r3:Region {id: "region_somalia"})
  SET r3.name = "Somalia", r3.country = "Somalia", r3.admin_level = 0,
      r3.current_risk_score = 0.0, r3.pagerank_score = 0.0, r3.current_regime = "regime_baseline";

MERGE (r4:Region {id: "region_sudan"})
  SET r4.name = "Sudan", r4.country = "Sudan", r4.admin_level = 0,
      r4.current_risk_score = 0.0, r4.pagerank_score = 0.0, r4.current_regime = "regime_baseline";

MERGE (r5:Region {id: "region_south_sudan"})
  SET r5.name = "South Sudan", r5.country = "South Sudan", r5.admin_level = 0,
      r5.current_risk_score = 0.0, r5.pagerank_score = 0.0, r5.current_regime = "regime_baseline";

MERGE (r6:Region {id: "region_uganda"})
  SET r6.name = "Uganda", r6.country = "Uganda", r6.admin_level = 0,
      r6.current_risk_score = 0.0, r6.pagerank_score = 0.0, r6.current_regime = "regime_baseline";

MERGE (r7:Region {id: "region_djibouti"})
  SET r7.name = "Djibouti", r7.country = "Djibouti", r7.admin_level = 0,
      r7.current_risk_score = 0.0, r7.pagerank_score = 0.0, r7.current_regime = "regime_baseline";

MERGE (r8:Region {id: "region_eritrea"})
  SET r8.name = "Eritrea", r8.country = "Eritrea", r8.admin_level = 0,
      r8.current_risk_score = 0.0, r8.pagerank_score = 0.0, r8.current_regime = "regime_baseline";

MERGE (r9:Region {id: "region_tanzania"})
  SET r9.name = "Tanzania", r9.country = "Tanzania", r9.admin_level = 0,
      r9.current_risk_score = 0.0, r9.pagerank_score = 0.0, r9.current_regime = "regime_baseline";

MERGE (r10:Region {id: "region_burundi"})
  SET r10.name = "Burundi", r10.country = "Burundi", r10.admin_level = 0,
      r10.current_risk_score = 0.0, r10.pagerank_score = 0.0, r10.current_regime = "regime_baseline";

MERGE (r11:Region {id: "region_rwanda"})
  SET r11.name = "Rwanda", r11.country = "Rwanda", r11.admin_level = 0,
      r11.current_risk_score = 0.0, r11.pagerank_score = 0.0, r11.current_regime = "regime_baseline";

// -----------------------------------------------------------
// 6. Seed: Intervention Strategies with RECOMMENDED_FOR
// -----------------------------------------------------------
MERGE (is1:InterventionStrategy {id: "strategy_early_warning"})
  SET is1.name = "Early Warning System Activation",
      is1.description = "Activate community-based early warning and disseminate alerts",
      is1.lead_time_days = 7;

MERGE (is2:InterventionStrategy {id: "strategy_water_trucking"})
  SET is2.name = "Emergency Water Trucking",
      is2.description = "Provide emergency water supply to drought-affected areas",
      is2.lead_time_days = 3;

MERGE (is3:InterventionStrategy {id: "strategy_sandbagging"})
  SET is3.name = "Flood Defences & Sandbagging",
      is3.description = "Deploy sandbags and temporary flood barriers in high-risk zones",
      is3.lead_time_days = 2;

// RECOMMENDED_FOR: InterventionStrategy → HazardRegime
MATCH (is1:InterventionStrategy {id: "strategy_early_warning"})
MATCH (hr1:HazardRegime {id: "regime_drought_onset"})
MERGE (is1)-[:RECOMMENDED_FOR {priority: 1}]->(hr1);

MATCH (is1:InterventionStrategy {id: "strategy_early_warning"})
MATCH (hr3:HazardRegime {id: "regime_flood_watch"})
MERGE (is1)-[:RECOMMENDED_FOR {priority: 1}]->(hr3);

MATCH (is2:InterventionStrategy {id: "strategy_water_trucking"})
MATCH (hr2:HazardRegime {id: "regime_severe_drought"})
MERGE (is2)-[:RECOMMENDED_FOR {priority: 1}]->(hr2);

MATCH (is3:InterventionStrategy {id: "strategy_sandbagging"})
MATCH (hr4:HazardRegime {id: "regime_flood_emergency"})
MERGE (is3)-[:RECOMMENDED_FOR {priority: 1}]->(hr4);

// -----------------------------------------------------------
// 7. INIT_REGIME relationships (Region → HazardRegime)
// -----------------------------------------------------------
MATCH (r:Region)
MATCH (hr:HazardRegime {id: "regime_baseline"})
MERGE (r)-[:IN_REGIME {since: datetime()}]->(hr);

// -----------------------------------------------------------
// 8. Seed: DataSource (ICPAC)
// -----------------------------------------------------------
MERGE (ds:DataSource {id: "datasource_icpac_rss"})
  SET ds.name = "ICPAC RSS Feed",
      ds.url = "https://www.icpac.net/feed/",
      ds.ingested_at = datetime(),
      ds.record_count = 0,
      ds.hash = "";

println("=== Schema 001 applied successfully ===");