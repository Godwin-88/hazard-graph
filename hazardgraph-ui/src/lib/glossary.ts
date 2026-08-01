/**
 * HazardGraph — Domain glossary for hover tooltips.
 *
 * Each entry provides a plain-language definition, a LaTeX formula
 * (rendered with KaTeX), and an IGAD-meteorological-facing definition.
 */

export interface GlossaryEntry {
  term: string
  definition: string
  formula: string
  igad: string
}

export const GLOSSARY: Record<string, GlossaryEntry> = {
  // ── Risk / scoring ───────────────────────────────────
  'Risk Score': {
    term: 'Risk Score',
    definition:
      'A 0–100 composite measure of a region\'s compound hazard risk, combining climatological, food-security, and network signals.',
    formula: 'R_i = \\sum_{j=1}^{5} w_j \\, C_{ij}',
    igad:
      'In the IGAD context, the Risk Score ranks Member States to prioritise early-warning resource allocation across the Horn of Africa.',
  },
  'BMA Posterior': {
    term: 'BMA Posterior',
    definition:
      'Bayesian Model Averaging combines forecasts from multiple models weighted by their posterior probability of being the best model.',
    formula: 'p(y|D) = \\sum_{k} p(y|M_k)\\, p(M_k|D)',
    igad:
      'For IGAD, BMA blends CHIRPS rainfall, HMM regime, SDE, and ML signals into one climatically robust drought probability.',
  },
  'Kelly Priority': {
    term: 'Kelly Priority',
    definition:
      'An alert-scoring heuristic derived from the Kelly criterion, ranking alerts by expected informational value per recipient.',
    formula: 'Kelly_t = \\frac{b\\,p - q}{b}',
    igad:
      'Used to decide which IGAD advisories to SMS first, maximising the chance a smallholder acts before a hazard peaks.',
  },
  'Vulnerability Multiplier': {
    term: 'Vulnerability Multiplier',
    definition:
      'A factor scaling raw hazard risk by socio-economic vulnerability (poverty, conflict, coping capacity) of a region.',
    formula: 'R_{adj} = R_{raw} \\times v_i',
    igad:
      'In the Horn of Africa, a pastoralist community with weak coping capacity receives a higher effective risk for the same rainfall deficit.',
  },
  'Compound Risk': {
    term: 'Compound Risk',
    definition:
      'The risk from the interaction of multiple overlapping hazards (drought + conflict + market shock) rather than any single one.',
    formula: 'R_{compound} = 1 - \\prod_{i}(1 - R_i)',
    igad:
      'Captures situations common in IGAD today: a drought in Somalia compounded by conflict and food-price spikes.',
  },

  // ── Climate / regime ────────────────────────────────
  'Climate Regime': {
    term: 'Climate Regime',
    definition:
      'A persistent hidden state of the climate system — baseline, drought onset, severe drought, flood watch — inferred over time.',
    formula: 's_t \\sim \\text{Categorical}(\\pi_{s_{t-1}})',
    igad:
      'HazardGraph assigns each IGAD region a regime (e.g. DroughtOnset) to trigger the appropriate advisory text and severity.',
  },
  HMM: {
    term: 'HMM',
    definition:
      'Hidden Markov Model: infers unobserved climate regimes from observed rainfall/vegetation series.',
    formula: 'P(X|\\lambda) = \\sum_{S} \\prod_{t} a_{s_{t-1}s_t} b_{s_t}(x_t)',
    igad:
      'The HMM learns the typical seasonal rhythm of the Horn of Africa to flag when a region drifts from normal rainfall.',
  },
  SPI: {
    term: 'SPI',
    definition:
      'Standardized Precipitation Index: a normalized measure of rainfall deficit/surplus over a fixed period, in standard deviations.',
    formula: 'SPI = \\frac{X - \\mu}{\\sigma}',
    igad:
      'IGAD uses SPI windows (1-, 3-, 6-month) to classify meteorological drought severity across its member states.',
  },
  NDVI: {
    term: 'NDVI',
    definition:
      'Normalized Difference Vegetation Index: a satellite measure of vegetation greenness used to detect crop/vegetation stress.',
    formula: 'NDVI = \\frac{NIR - Red}{NIR + Red}',
    igad:
      'Over IGAD rangelands and croplands, falling NDVI reveals vegetation water stress weeks before IPC classification shifts.',
  },

  // ── Forecast / ML ───────────────────────────────────
  LSTM: {
    term: 'LSTM',
    definition:
      'Long Short-Term Memory: a recurrent neural network that learns long-range dependencies in time series for forecasting.',
    formula: 'f_t = \\sigma(W_f \\cdot [h_{t-1}, x_t] + b_f)',
    igad:
      'BiLSTM forecasts the future IPC phase of a region by learning from its multi-year rainfall and food-price history.',
  },
  XGBoost: {
    term: 'XGBoost',
    definition:
      'Extreme Gradient Boosting: an ensemble of decision trees optimized greedily for predictive accuracy and feature importance.',
    formula: '\\hat{y} = \\sum_{k} f_k(x), \\quad f_k \\in \\mathcal{F}',
    igad:
      'Predicts the probability of a food crisis (P_crisis) in an IGAD region and lists its top SHAP driving features.',
  },
  SHAP: {
    term: 'SHAP',
    definition:
      'SHapley Additive exPlanations: a game-theoretic method that attributes a prediction to each input feature.',
    formula: '\\phi_i = \\sum_{S \\subseteq N \\setminus \\{i\\}} \\frac{|S|!(|N|-|S|-1)!}{|N|!} [f(S \\cup \\{i\\}) - f(S)]',
    igad:
      'Reveals which driver (e.g. rainfall, IPC phase, maize price) pushed a region\'s crisis probability up or down.',
  },
  SDE: {
    term: 'SDE',
    definition:
      'Stochastic Differential Equation: a rainfall model with a deterministic trend plus random noise (Brownian motion) to project drought/flood probabilities.',
    formula: 'dX_t = \\mu(X_t, t)\\, dt + \\sigma\\, dW_t',
    igad:
      'Simulates 4-week ahead probabilities of drought, flood, or severe conditions for each IGAD region.',
  },
  'P(Crisis)': {
    term: 'P(Crisis)',
    definition:
      'Probability that a region enters an IPC Phase 3+ food crisis within the forecast horizon, output by the XGBoost model.',
    formula: 'P(Crisis) \\in [0,1]',
    igad:
      'A probability above ~0.5 for an IGAD region triggers heightened monitoring and pre-emptive advisory issuance.',
  },
  'IPC Phase': {
    term: 'IPC Phase',
    definition:
      'The Integrated Food Security Phase Classification: a 1–5 scale from Minimal to Famine describing acute food insecurity.',
    formula: 'Phase \\in \\{1,2,3,4,5\\}',
    igad:
      'The lingua franca of food security in the Horn of Africa — IGAD coordinates responses based on IPC phases across member states.',
  },
  'Model Agreement': {
    term: 'Model Agreement',
    definition:
      'A measure of how consistently LSTM, XGBoost, SDE, and BMA agree on a region\'s forecast direction — high agreement means higher confidence.',
    formula: 'Agreement = \\frac{\\text{models agreeing}}{\\text{total models}}',
    igad:
      'When all models flag Somalia as critical together, decision-makers can trust the signal more than when models disagree.',
  },

  // ── Causal / network ────────────────────────────────
  VARLiNGAM: {
    term: 'VARLiNGAM',
    definition:
      'Vector AutoRegression + Linear Non-Gaussian Acyclic Model: discovers causal direction from lagged time-series data.',
    formula: 'X_t = \\sum_{k=1}^{p} B_k X_{t-k} + \\epsilon_t, \\quad \\epsilon \\text{ non-Gaussian}',
    igad:
      'Learns whether, e.g., low rainfall causes food-price spikes in a region, or the reverse — revealing true drivers of food crises.',
  },
  'Causal Edge': {
    term: 'Causal Edge',
    definition:
      'A directed relationship in the causal graph indicating one variable causally influences another, with a weight and lag.',
    formula: 'x_s \\xrightarrow{\\;w,\\; \\ell\\;} x_t',
    igad:
      'Each edge links a driver (e.g. rainfall) to an outcome (e.g. IPC phase) with a strength w and lag in weeks specific to an IGAD region.',
  },
  'Causal Chain': {
    term: 'Causal Chain',
    definition:
      'A directed path from a root cause through intermediate variables to a hazard outcome, with cumulative chain weight.',
    formula: 'W_{chain} = \\sum_{(u,v) \\in path} w_{uv}',
    igad:
      'Traces how a rainfall deficit cascades through crop prices to reach a food-security emergency in a specific IGAD locality.',
  },
  PageRank: {
    term: 'PageRank',
    definition:
      'A network centrality algorithm scoring node importance by the quantity and quality of incoming links.',
    formula: 'PR(v) = \\frac{1-d}{N} + d \\sum_{u \\in B_v} \\frac{PR(u)}{L(u)}',
    igad:
      'Identifies the most "network-critical" IGAD regions — the ones whose failure drags down interconnected neighbours via trade and climate links.',
  },
  'Louvain Cluster': {
    term: 'Louvain Cluster',
    definition:
      'A community-detection algorithm that groups regions into hazard clusters by maximizing modularity.',
    formula: 'Q = \\frac{1}{2m} \\sum_{ij} \\left[ A_{ij} - \\frac{k_i k_j}{2m} \\right] \\delta(c_i, c_j)',
    igad:
      'Groups IGAD regions into aid-allocation clusters sharing similar hazard exposure, so resources can be pooled efficiently.',
  },
  'SIR Cascade': {
    term: 'SIR Cascade',
    definition:
      'Susceptible–Infected–Recovered model simulating how a crisis (e.g. food insecurity) spreads through the region network.',
    formula: '\\frac{dS}{dt} = -\\beta S I, \\quad \\frac{dI}{dt} = \\beta S I - \\gamma I, \\quad \\frac{dR}{dt} = \\gamma I',
    igad:
      'Projects which IGAD neighbours a food crisis from one region will spill over into, and identifies the best "chain-breaker" intervention point.',
  },

  // ── RL / prescriptive ───────────────────────────────
  'GNN-PPO': {
    term: 'GNN-PPO',
    definition:
      'A Graph Neural Network policy trained with Proximal Policy Optimization to choose optimal alert actions per region.',
    formula: 'L^{CLIP}(\\theta) = \\mathbb{E}_t\\left[\\min(r_t(\\theta)\\hat{A}_t, \\text{clip}(r_t(\\theta), 1-\\epsilon, 1+\\epsilon)\\hat{A}_t)\\right]',
    igad:
      'Learns from historical IGAD alerts and outcomes whether to issue no alert, an SMS advisory, or an escalation for each region.',
  },
  Policy: {
    term: 'Policy',
    definition:
      'In reinforcement learning, a policy maps a state (graph of regional risks) to a distribution over alert actions.',
    formula: '\\pi(a|s) = \\Pr(A_t = a \\mid S_t = s)',
    igad:
      'The policy encodes a decision rule for IGAD coordinators: given current risks, which alert actions maximise warning effectiveness.',
  },
  Reward: {
    term: 'Reward',
    definition:
      'A scalar signal encouraging beneficial outcomes in RL — here, correct, well-timed alerts that reduce affected populations.',
    formula: 'R_t = \\alpha \\cdot \\text{timeliness} - \\beta \\cdot \\text{false\\ alarm}',
    igad:
      'Rewards IGAD-optimal behaviour: alerting before a hazard peaks while minimising false alarms that erode community trust in SMS warnings.',
  },

  // ── Ops / pipeline ──────────────────────────────────
  DAG: {
    term: 'DAG',
    definition:
      'Directed Acyclic Graph: the pipeline structure of dependencies where data flows from ingestion through modelling to output, with no cycles.',
    formula: 'nodes: V, \\quad edges: E \\subseteq V \\times V',
    igad:
      'Defines the reproducible order HazardGraph executes — ingest CHIRPS/WFP/IPC, then model, score, and generate advisories for IGAD.',
  },
  Ingestion: {
    term: 'Ingestion',
    definition:
      'The pipeline stage that fetches raw external data (CHIRPS rainfall, WFP prices, IPC phases, ICPAC RSS) and writes it to the graph.',
    formula: 'D_{raw} \\xrightarrow{\\text{fetch}} D_{stored}',
    igad:
      'Continuously pulls the meteorological and market datasets that keep IGAD early-warning fresh.',
  },
   'Alert Action': {
     term: 'Alert Action',
     definition:
       'The prescribed response level for a region — from no alert, through SMS advisory and text, to high escalation.',
     formula: 'a \\in \\{\\text{NO\\_ALERT}, \\text{LOW\\_ADVISORY}, \\text{MEDIUM\\_SMS}, \\text{HIGH\\_ESCALATE}\\}',
     igad:
       'Tells the IGAD coordination desk the strength of communication to use for each at-risk area, calibrated to avoid alarm fatigue.',
   },

   // ── Navigation labels (header tooltips) ─────────────
   'Graph Explorer': {
     term: 'Graph Explorer',
     definition:
       'Interactive view of the causal knowledge graph: regions, climate regimes, and rainfall/food-price/IPC signals as nodes connected by discovered causal edges.',
     formula: 'G = (V, E), \\quad E \\subseteq V \\times V',
     igad:
       'Lets IGAD analysts inspect how hazards and signals interlink across member states and trace the causal chain behind a food crisis.',
   },
   'Forecast & Analytics': {
     term: 'Forecast & Analytics',
     definition:
       'The panel of machine-learning forecasts (LSTM, XGBoost, SDE, BMA) and descriptive analytics for each IGAD region.',
     formula: '\\hat{y}_t = f(x_{1..t}), \\quad \\text{Agreement} = \\frac{\\text{models agreeing}}{\\text{total models}}',
     igad:
       'Brings together all predictive signals — rainfall, food prices, IPC phases — so early-warning officers see a single forward-looking picture.',
   },
   'Simulate & Run': {
     term: 'Simulate & Run',
     definition:
       'The workspace for prescriptive analytics: DRL policy actions, contagion cascades, aid clusters, and on-demand execution of the ML pipeline and models.',
     formula: '\\pi(a|s) \\to a^*, \\quad \\text{cascade}(S, I, R)',
     igad:
       'Lets IGAD simulate how a crisis spreads through the region network and run models on demand to test "what-if" intervention scenarios.',
   },
   'Alert Review': {
     term: 'Alert Review',
     definition:
       'The officer queue for approving, editing, rejecting, and dispatching SMS advisories generated for at-risk regions.',
     formula: 'a \\in \\{\\text{NO\\_ALERT}, \\text{LOW\\_ADVISORY}, \\text{MEDIUM\\_SMS}, \\text{HIGH\\_ESCALATE}\\}',
     igad:
       'The human-in-the-loop checkpoint where IGAD coordinators confirm advisories before they are sent to farmers by SMS.',
   },

   // ── Common node property names (node-detail modal) ──
   'SPI 30D': {
     term: 'SPI 30D',
     definition:
       'Standardized Precipitation Index computed over a 30-day window — a normalized measure of recent rainfall deficit or surplus.',
     formula: 'SPI_{30} = \\frac{X_{30} - \\mu_{30}}{\\sigma_{30}}',
     igad:
       'A strongly negative SPI-30 flags an acute short-term rainfall shortfall in an IGAD region, a leading indicator of drought onset.',
   },
   'Spread 30D Smoothed': {
     term: 'SPI 30D Smoothed',
     definition:
       'A temporally smoothed version of the 30-day SPI used to filter out single-dekad noise and reveal the underlying trend.',
     formula: '\\tilde{x}_t = \\sum_{k} w_k\\, x_{t-k}',
     igad:
       'Smoothing separates genuine dry spells from temporary dips, giving IGAD forecasters a steadier rainfall signal.',
   },
   'Anomaly Pct': {
     term: 'Anomaly Pct',
     definition:
       'The percentage deviation of current rainfall from the long-term climatological average for the same period.',
     formula: '\\text{Anom\\%} = 100 \\times \\frac{P - \\bar{P}}{\\bar{P}}',
     igad:
       'A large negative anomaly indicates the rains have failed relative to the expected seasonal climatology for that IGAD region.',
   },
   'Commodity': {
     term: 'Commodity',
     definition:
       'The staple food item (e.g. maize, wheat, sorghum, rice) whose market price is tracked for a region.',
     formula: 'C \\in \\{\\text{maize}, \\text{wheat}, \\text{sorghum}, \\ldots \\}',
     igad:
       'IGAD tracks staple commodities whose price swings most directly affect household food access in the Horn of Africa.',
   },
   'Price USD': {
     term: 'Price USD',
     definition:
       'The local market price of a food commodity expressed in US dollars for cross-country comparability.',
     formula: 'P_{USD} = P_{local} \\times \\text{FX}',
     igad:
       'Converting to USD lets IGAD compare food prices between states despite different currencies and inflation rates.',
   },
   'Pct Change 30D': {
     term: 'Pct Change 30D',
     definition:
       'The percentage change in a commodity price over the trailing 30 days — a rapid rise signals market stress.',
     formula: '\\Delta_{30} = \\frac{P_t - P_{t-30}}{P_{t-30}}',
     igad:
       'A sharp 30-day price spike in an IGAD market often precedes food-access crises and conflict-driven displacement.',
   },
   'Population Affected': {
     term: 'Population Affected',
     definition:
       'The number of people estimated to be in IPC Phase 3+ (Crisis and above) in a region at a given reference date.',
     formula: 'N_{affected} = \\sum_{phase \\geq 3} pop_{phase}',
     igad:
       'This magnitude informs IGAD humanitarian resource targets and the scale of SMS alert distribution needed.',
   },
   'Reference Date': {
     term: 'Reference Date',
     definition:
       'The date to which an analysis, forecast, or IPC classification snapshot applies.',
     formula: 't_{ref} \\in \\mathbb{R}_{\\geq 0}',
     igad:
       'Ensures all IGAD signals are aligned in time so early-warning comparisons across regions are apples-to-apples.',
   },
   'Current Risk Score': {
     term: 'Current Risk Score',
     definition:
       'The latest composite 0–100 risk score assigned to a region as of the most recent scoring run.',
     formula: 'R_{t} \\in [0, 100]',
     igad:
       'The current score drives which IGAD regions are placed on the watchlist and prioritised for alert generation.',
   },
   'Current Regime': {
     term: 'Current Regime',
     definition:
       'The present inferred climate regime of a region — Baseline, DroughtOnset, SevereDrought, FloodWatch, or FloodEmergency.',
     formula: 's_t \\in \\{\\text{Baseline}, \\text{DroughtOnset}, \\ldots \\}',
     igad:
       'Determines the advisory tone and SMS content IGAD sends to farmers for that region.',
   },
   'Severity Level': {
     term: 'Severity Level',
     definition:
       'A 0–4 scale classifying how severe a climate regime or hazard is, from normal to emergency.',
     formula: 'sev \\in \\{0,1,2,3,4\\}',
     igad:
       'Matches IGAD disaster-management tiers so response effort scales with declared severity.',
   },
   'Pagerank Score': {
     term: 'PageRank Score',
     definition:
       'A network-centrality score reflecting how structurally important a region is in the IGAD hazard-interdependency graph.',
     formula: 'PR(v) = \\frac{1-d}{N} + d \\sum_{u \\in B_v} \\frac{PR(u)}{L(u)}',
     igad:
       'A high PageRank region is one whose failure would most drag down interconnected neighbours — a prioritisation signal for IGAD.',
   },
   'Lag Days': {
     term: 'Lag Days',
     definition:
       'The number of days by which a cause leads its effect along a causal edge in the knowledge graph.',
     formula: '\\ell \\in \\mathbb{Z}_{\\geq 0}',
     igad:
       'The lag reveals how many days of lead warning IGAD can expect between a driver signal and its downstream impact.',
   },
   'Weight': {
     term: 'Weight',
     definition:
       'The strength of a causal relationship or ensemble-model contribution; higher magnitude means stronger influence.',
     formula: 'w_{uv} \\in [-1, 1]',
     igad:
       'Weights rank which causal drivers matter most for an IGAD region, guiding where to intervene first.',
   },
 }
