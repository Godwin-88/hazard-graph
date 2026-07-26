# HazardGraph v2.0 — Augmented Product Specification
## A Quantifaya Weather & Climate Intelligence Platform
### IGAD Hackathon 2026 | Powered by the GraphAlpha Quantitative Engine

**Author:** Godwin Edgar Opuka | Quantifaya
**Version:** 2.0 — Model-Augmented Architecture
**Reference graphs:** `capability_canvas.cypher` (Enterprise Architecture) +
`master.cypher` (GraphAlpha Financial Engineering Ontology)

---

> **Brand Vision:** HazardGraph is the first product in the
> **Quantifaya Climate Intelligence Suite** — a long-term platform applying
> quantitative finance methods (stochastic processes, regime detection, network
> science, Bayesian inference) to weather, climate, and food security modelling
> for African markets. The same mathematical DNA that powers GraphAlpha (options
> pricing, vol regimes, causal graphs) is repurposed here for humanitarian
> intelligence. One brand. Two domains. Same rigour.

---

## How GraphAlpha Maps to HazardGraph

The `master.cypher` graph uses this ontology:
```
Regime → Strategy → Concept → Formula → Parameter
```

HazardGraph adopts the **identical structure**, renamed for climate:

| GraphAlpha (Finance) | HazardGraph (Climate) |
|---|---|
| `Regime` (Trending, Crisis, HighVol) | `HazardRegime` (Drought, Flood, LocustOutbreak, FoodCrisis) |
| `Strategy` (Momentum Breakout, Vol Mean Reversion) | `InterventionStrategy` (EarlyHarvest, LivestockDestocking, WaterHarvesting) |
| `Concept` (Heston Model, VARLiNGAM, Jump Diffusion) | `ClimateModel` (ENSO Oscillation, SPI, NDVI, Excess Rainfall Index) |
| `Formula` (BS Call, Sharpe, Kelly) | `ClimateFormula` (SPI formula, NDVI anomaly, flood return period) |
| `Signal` (runtime trade signal) | `HazardSignal` (runtime alert signal) |
| `ACTIVATED_BY` (Strategy → Regime) | `RECOMMENDED_FOR` (Intervention → HazardRegime) |
| `CONTRADICTED_BY` (Strategy → Strategy) | `CONFLICTS_WITH` (Intervention → Intervention) |
| `PREREQ_OF` (Concept → Concept) | `PRECEDES` (ClimateEvent → ClimateEvent) |

This is not metaphor — it is the same graph traversal logic, the same Cypher
query patterns, and the same Neo4j schema engine, extended with climate domain
nodes.

---

## Full Quantitative Model Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    QUANTIFAYA CLIMATE INTELLIGENCE ENGINE                    │
│                                                                             │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────────┐  │
│  │  LAYER 1         │  │  LAYER 2         │  │  LAYER 3                 │  │
│  │  Stochastic      │  │  Machine         │  │  Network                 │  │
│  │  Process Models  │  │  Learning        │  │  Science                 │  │
│  │                  │  │  Models          │  │  Models                  │  │
│  │  • SDE for SPI   │  │  • LSTM Drought  │  │  • PageRank Vulnerability│  │
│  │  • Jump-Diffusion│  │  • XGBoost IPC   │  │  • Contagion Cascade     │  │
│  │    Rainfall      │  │  • CNN Satellite  │  │  • Community Detection   │  │
│  │  • CIR Vol Model │  │  • Prophet NDVI  │  │  • Centrality Alerting   │  │
│  │  • Kalman Filter │  │  • Transformer   │  │  • Bipartite Region-     │  │
│  │  • HMM Regime    │  │    Forecast      │  │    Hazard Matching       │  │
│  └──────────┬───────┘  └──────────┬───────┘  └──────────┬───────────────┘  │
│             │                     │                      │                  │
│             └─────────────────────┴──────────────────────┘                  │
│                                   │                                         │
│                                   ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │              LAYER 4: CAUSAL KNOWLEDGE GRAPH (Neo4j)                │    │
│  │  VARLiNGAM edges + GraphAlpha Regime/Strategy/Concept ontology      │    │
│  │  HazardRegime → InterventionStrategy → ClimateModel → Formula       │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                   │                                         │
│                                   ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │           LAYER 5: COMPOUND RISK SCORING ENGINE                     │    │
│  │   Bayesian Model Averaging across all Layer 1–3 outputs             │    │
│  │   Kelly-fractional alert prioritisation (from GraphAlpha)           │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                   │                                         │
│                                   ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │        LAYER 6: DISSEMINATION (SMS + Dashboard + API)               │    │
│  │        Africa's Talking | React UI | FastAPI | Redis                │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# EPIC-07 — Stochastic Process Models (Layer 1)

> **Goal:** Model climate signal dynamics as stochastic processes — applying
> the same mathematical machinery as GraphAlpha's `CIR Process`,
> `Geometric Brownian Motion`, and `Jump Diffusion` concepts, now calibrated
> to rainfall, vegetation, and food price time series.
>
> _GraphAlpha reference: `Concept {name: 'CIR Process'}`,
> `Concept {name: 'Jump Diffusion'}`, `Concept {name: 'Heston Model'}`,
> `Regime {name: 'HighVolatility'}` → maps to `HazardRegime {name: 'FloodBurst'}`_

---

## FEAT-07-A: SDE Rainfall Model (CIR + Jump Diffusion)

### User Story 07-A-1
**As a** climate modeller,
**I want** rainfall anomalies modelled as a mean-reverting jump-diffusion
stochastic process,
**So that** the system can compute the probability of extreme rainfall events
(flood triggers) beyond what simple threshold rules catch.

#### Model Specification

```
Rainfall SDE (adapted CIR with jumps):

  dR(t) = κ(θ - R(t))dt + σ√R(t) dW(t) + J·dN(t)

where:
  R(t)  = rainfall anomaly (SPI units)
  κ     = mean-reversion speed (calibrated to historical SPI autocorrelation)
  θ     = long-run SPI mean (≈ 0 by definition of SPI)
  σ     = volatility of rainfall variability
  W(t)  = standard Brownian motion
  J     ~ Exponential(λ_j) — jump size (ENSO-driven extreme rainfall events)
  N(t)  = Poisson process with intensity λ_p (jump arrival rate)

Feller condition for positivity: 2κθ > σ² (same condition as GraphAlpha CIR)

Calibration:
  - κ, σ: MLE on 30-year CHIRPS monthly SPI per region
  - λ_p:  historical extreme event frequency (SPI < -1.5 or > 1.5)
  - λ_j:  mean jump magnitude from historical extremes

Output per region per week:
  P(flood | current R(t)) = P(R(t+h) > threshold | R(t))
  P(drought | current R(t)) = P(R(t+h) < -1.0 | R(t))
  computed via 10,000-path Monte Carlo simulation
```

#### Acceptance Criteria
- [ ] `SDE` class in `models/stochastic/rainfall_sde.py` implementing CIR + jump
- [ ] Calibration method: `fit(spi_series: pd.Series) -> HestonParams` using
  `scipy.optimize` (mirrors GraphAlpha's Heston calibrator)
- [ ] Monte Carlo: 10,000 paths, 4-week horizon, vectorised with `numpy`
- [ ] Output: `{p_flood_4w, p_drought_4w, current_vol, jump_intensity}` per region
- [ ] Runs weekly after CHIRPS ingestion
- [ ] Results stored as `StochasticSignal` nodes in Neo4j
- [ ] Unit test: Feller condition check, path simulation shape validation

#### Tasks
- [ ] `T-07-A-1-1` `models/stochastic/rainfall_sde.py` — CIR + jump SDE
- [ ] `T-07-A-1-2` `models/stochastic/calibrator.py` — MLE calibration
- [ ] `T-07-A-1-3` `models/stochastic/mc_simulator.py` — vectorised MC
- [ ] `T-07-A-1-4` Neo4j `StochasticSignal` node writer
- [ ] `T-07-A-1-5` Weekly cron integration
- [ ] `T-07-A-1-6` Unit + integration tests

---

## FEAT-07-B: Hidden Markov Model — Climate Regime Detection

### User Story 07-B-1
**As a** risk analyst,
**I want** the system to automatically detect which climate regime each region
is in (analogous to GraphAlpha's market regimes),
**So that** the intervention recommendation engine activates the right
strategies for the current hazard state.

#### Model Specification

```
Climate Regime HMM:

  Hidden states S ∈ {Dry, Normal, Wet, ExtremeDry, ExtremeWet}
  Observed variables O = [SPI_30, NDVI_anomaly, FoodPrice_pct_change, IPC_phase]

  HMM parameters:
    A = transition matrix (5×5) — calibrated on 20yr CHIRPS + IPC data
    B = emission distributions (Gaussian mixture per state per variable)
    π = initial state distribution

  Viterbi decoding → most likely current regime sequence
  Forward algorithm → P(current state | observations)

  Maps to GraphAlpha Regime nodes:
    Dry          → HazardRegime {name: 'DroughtOnset'}
    Normal       → HazardRegime {name: 'Baseline'}
    Wet          → HazardRegime {name: 'FloodWatch'}
    ExtremeDry   → HazardRegime {name: 'SevereDrought'}   [Crisis equivalent]
    ExtremeWet   → HazardRegime {name: 'FloodEmergency'}  [Crisis equivalent]
```

#### Acceptance Criteria
- [ ] `models/regime/climate_hmm.py` using `hmmlearn.GaussianHMM`
- [ ] 5 hidden states, 4 observed variables
- [ ] Trained on all available CHIRPS + IPC history (minimum 10 years per region)
- [ ] Viterbi path stored in `Region.current_regime` (Neo4j property)
- [ ] `HazardRegime` nodes created in Neo4j, linked to regions via
  `IN_REGIME` relationship
- [ ] `InterventionStrategy` nodes linked to `HazardRegime` via
  `RECOMMENDED_FOR` (mirrors GraphAlpha `ACTIVATED_BY`)
- [ ] Regime posterior probabilities cached in Redis (1hr TTL)
- [ ] Dashboard: regime badge per region (colour coded, 5 states)

#### Tasks
- [ ] `T-07-B-1-1` `models/regime/climate_hmm.py`
- [ ] `T-07-B-1-2` Training pipeline: assemble multivariate observation matrix
- [ ] `T-07-B-1-3` `HazardRegime` + `InterventionStrategy` Neo4j seeder
  (mirroring GraphAlpha's Regime/Strategy Cypher pattern)
- [ ] `T-07-B-1-4` `RECOMMENDED_FOR` relationship writer
- [ ] `T-07-B-1-5` Redis posterior caching
- [ ] `T-07-B-1-6` React `RegimeBadge` component (shadcn `Badge` variants)

---

## FEAT-07-C: Kalman Filter — Real-Time Signal Smoothing

### User Story 07-C-1
**As a** data engineer,
**I want** noisy satellite observations (NDVI, rainfall) smoothed via Kalman
filtering before they enter the causal graph,
**So that** signal quality is high and causal edge weights are not distorted
by measurement noise.

#### Model Specification

```
Linear Kalman Filter per signal per region:

  State: x(t) = [SPI(t), ΔSPI(t)]  (level + rate-of-change)
  Observation: z(t) = SPI_observed(t) + ε,  ε ~ N(0, R)

  Prediction:   x̂(t|t-1) = F·x(t-1|t-1)
  Update:       x̂(t|t)   = x̂(t|t-1) + K(t)·(z(t) - H·x̂(t|t-1))
  Kalman gain:  K(t) = P(t|t-1)·Hᵀ·(H·P(t|t-1)·Hᵀ + R)⁻¹

  Q, R calibrated per region via EM algorithm on historical data
```

#### Acceptance Criteria
- [ ] `models/filtering/kalman.py` using `filterpy.kalman.KalmanFilter`
- [ ] Applied to SPI and NDVI before graph ingestion
- [ ] Smoothed signal replaces raw in `RainfallSignal.spi_30d_smoothed`
- [ ] Innovation (residual) stored: large innovations flag data quality issues

#### Tasks
- [ ] `T-07-C-1-1` `models/filtering/kalman.py`
- [ ] `T-07-C-1-2` EM calibration for Q, R per region
- [ ] `T-07-C-1-3` Integration into CHIRPS ingestion pipeline (post-download)
- [ ] `T-07-C-1-4` Innovation anomaly detector → data quality alert

---

# EPIC-08 — Machine Learning Models (Layer 2)

> **Goal:** Augment the stochastic and causal models with supervised ML for
> higher-accuracy short-term forecasting of IPC phases and drought severity.
>
> _GraphAlpha reference: `Category {name: 'estimation'}`,
> `Category {name: 'dimensionality_reduction'}` — same estimation rigour
> applied to climate ML feature engineering._

---

## FEAT-08-A: LSTM Drought Severity Forecaster

### User Story 08-A-1
**As a** humanitarian planner,
**I want** a 4-week ahead forecast of drought severity (IPC phase) per region
from a deep learning model,
**So that** I have a data-driven probability estimate to cross-validate against
the stochastic SDE model.

#### Model Specification

```
Bidirectional LSTM Ensemble:

  Input:  X(t) = [SPI_30, SPI_90, NDVI_anomaly, FoodPrice_pct,
                  rainfall_trend_slope, IPC_phase_lag1, IPC_phase_lag4,
                  ENSO_index, IOD_index]  → shape (T=52, F=9)

  Architecture:
    BiLSTM(128 units) → Dropout(0.3)
    BiLSTM(64 units)  → Dropout(0.2)
    Dense(32, ReLU)
    Dense(5, Softmax) → P(IPC phase ∈ {1,2,3,4,5})

  Loss:       Categorical cross-entropy with class weights
              (Phase 4/5 upweighted 3× — cost-sensitive learning)
  Optimiser:  Adam(lr=1e-3) with cosine annealing
  Ensemble:   5 models with different random seeds → mean probability
  Training:   Leave-last-2-years-out cross-validation (era-aware, no leakage)
              [mirrors GraphAlpha era-aware CV from Numerai notebook]

  Output per region per week:
    {p_phase1, p_phase2, p_phase3, p_phase4, p_phase5,
     predicted_phase, confidence, model_agreement}
```

#### Acceptance Criteria
- [ ] `models/ml/lstm_drought.py` using `torch` (PyTorch)
- [ ] Input pipeline: 52-week rolling window per region assembled from Neo4j
- [ ] 5-model ensemble with agreement score
- [ ] Prediction stored: `MLForecast {model: "LSTM", horizon_weeks: 4,
  predicted_phase, confidence, region_id, created_at}`
- [ ] Era-aware train/val split: no validation leakage across time
- [ ] Retrained monthly (full), updated weekly (fine-tune)
- [ ] Performance logged: Brier score, AUC per phase per region
- [ ] Cost-sensitive weighting: Phase 4/5 misclassification costs 3×

#### Tasks
- [ ] `T-08-A-1-1` `models/ml/lstm_drought.py` — model definition
- [ ] `T-08-A-1-2` `models/ml/feature_pipeline.py` — 52-week window assembler
- [ ] `T-08-A-1-3` Training script with era-aware CV
- [ ] `T-08-A-1-4` Ensemble wrapper (5-model)
- [ ] `T-08-A-1-5` `MLForecast` Neo4j node writer
- [ ] `T-08-A-1-6` Monthly retrain + weekly fine-tune cron jobs
- [ ] `T-08-A-1-7` Performance metrics PostgreSQL table `model_performance`
- [ ] `T-08-A-1-8` FastAPI endpoint `GET /api/v1/forecast/lstm/{region_id}`

---

## FEAT-08-B: XGBoost Food Insecurity Early Warning

### User Story 08-B-1
**As a** food security analyst,
**I want** a gradient-boosted tree model that forecasts the probability of
IPC Phase ≥ 3 (Crisis) 8 weeks ahead,
**So that** I have an interpretable model with feature importance to explain
predictions to non-technical stakeholders.

#### Model Specification

```
XGBoost Binary Classifier:

  Target:   P(IPC_phase ≥ 3 in next 8 weeks) — binary
  Features: [SPI_30, SPI_90, SPI_180, NDVI_anom, price_maize_pct,
             price_sorghum_pct, conflict_events_30d, displacement_30d,
             HMM_regime_encoded, LSTM_p_phase3plus, SDE_p_drought_4w,
             lagged_IPC, seasonal_dummies (12 months)]

  Params:   n_estimators=500, max_depth=6, learning_rate=0.01,
            subsample=0.8, colsample_bytree=0.7,
            scale_pos_weight = (n_negative/n_positive)  [class imbalance]

  Calibration: Platt scaling on holdout set → calibrated probabilities
  Explainability: SHAP values computed for every prediction
                  Top 5 SHAP features included in alert advisory context

  Output: {p_crisis, calibrated_p, top5_shap_features, prediction_date}
```

#### Acceptance Criteria
- [ ] `models/ml/xgb_food_crisis.py` with `xgboost` + `shap`
- [ ] Calibrated probability output (Platt scaling)
- [ ] SHAP values computed for every live prediction
- [ ] Top 5 SHAP features passed to LLM advisory prompt as context
  (makes advisories causally grounded, not black-box)
- [ ] `XGBForecast` node in Neo4j linked to region
- [ ] Feature importance chart in React dashboard (recharts `BarChart`)
- [ ] Retrained monthly

#### Tasks
- [ ] `T-08-B-1-1` `models/ml/xgb_food_crisis.py`
- [ ] `T-08-B-1-2` SHAP integration + top-5 extractor
- [ ] `T-08-B-1-3` Platt scaling calibrator
- [ ] `T-08-B-1-4` LLM prompt context injection: SHAP features → advisory
- [ ] `T-08-B-1-5` React `FeatureImportanceChart` component
- [ ] `T-08-B-1-6` `XGBForecast` Neo4j writer

---

## FEAT-08-C: Satellite NDVI Anomaly Detection (CNN)

### User Story 08-C-1
**As a** remote sensing analyst,
**I want** vegetation stress detected directly from MODIS NDVI raster images
using a CNN,
**So that** the system identifies crop failure patterns 3–6 weeks earlier than
ground-reported IPC data allows.

#### Model Specification

```
Lightweight CNN Anomaly Detector:

  Input:  MODIS NDVI 250m raster → resized to 64×64 per admin-1 region
          Time series: current dekad vs same dekad previous 3 years (4 channels)

  Architecture:
    Conv2D(32, 3×3, ReLU) → MaxPool(2×2)
    Conv2D(64, 3×3, ReLU) → MaxPool(2×2)
    Conv2D(128, 3×3, ReLU) → GlobalAveragePool
    Dense(64, ReLU) → Dense(1, Sigmoid)

  Target:    P(NDVI anomaly < -0.15) — vegetation stress indicator
  Training:  Historical MODIS + historical IPC labels (2005–2024)
  Data:      NASA Earthdata free account — MODIS MOD13A1 product

  Output: {stress_probability, anomaly_magnitude, affected_area_pct}
```

#### Acceptance Criteria
- [ ] `models/ml/ndvi_cnn.py` using `torch` + `rasterio`
- [ ] MODIS data fetched via NASA Earthdata API (free account)
- [ ] 64×64 per region raster preprocessing pipeline
- [ ] Inference runs weekly post-MODIS update
- [ ] Stress probability stored as `NDVISignal` in Neo4j
- [ ] Raster thumbnail displayed in React region detail modal

#### Tasks
- [ ] `T-08-C-1-1` `models/ml/ndvi_cnn.py`
- [ ] `T-08-C-1-2` `data/modis_fetcher.py` — NASA Earthdata API integration
- [ ] `T-08-C-1-3` Raster preprocessing: crop + resize + normalise pipeline
- [ ] `T-08-C-1-4` `NDVISignal` Neo4j writer
- [ ] `T-08-C-1-5` React raster thumbnail in `RegionDetailModal`

---

## FEAT-08-D: Time-Series Foundation Model (Nixtla TimeGPT / Prophet Ensemble)

### User Story 08-D-1
**As a** platform administrator,
**I want** a zero-shot time series forecast for any climate variable using a
pre-trained foundation model,
**So that** new data sources can be forecasted without retraining custom models.

#### Model Specification

```
Ensemble: Facebook Prophet + Nixtla TimeGPT (zero-shot)

  Prophet component:
    - Trend: piecewise linear with change-point detection
    - Seasonality: monthly (ENSO annual cycle), dekadal
    - Regressors: ENSO index, IOD index as external regressors
    - Uncertainty: Monte Carlo samples → credible intervals

  TimeGPT component (Nixtla free tier):
    - Zero-shot inference via API
    - 12-week forecast horizon
    - Conformal prediction intervals

  Ensemble: weighted average (weight by recent RMSE on holdout)

  Covers: SPI_30, NDVI, maize price, sorghum price per region
```

#### Acceptance Criteria
- [ ] `models/ml/timeseries_ensemble.py`
- [ ] Prophet: `neuralprophet` library
- [ ] TimeGPT: Nixtla API (free tier: 5,000 calls/month)
- [ ] Ensemble weighting updated weekly based on rolling 4-week RMSE
- [ ] 12-week forecast stored: `TSForecast {variable, region, horizon_weeks: 12,
  values: [], lower_ci: [], upper_ci: []}`
- [ ] Forecast chart in React (recharts `AreaChart` with CI bands)

#### Tasks
- [ ] `T-08-D-1-1` `models/ml/timeseries_ensemble.py`
- [ ] `T-08-D-1-2` Nixtla API integration + rate limit manager
- [ ] `T-08-D-1-3` Ensemble weighting service
- [ ] `T-08-D-1-4` `TSForecast` Neo4j writer
- [ ] `T-08-D-1-5` React `ForecastChart` (recharts AreaChart + CI shading)
- [ ] `T-08-D-1-6` FastAPI `GET /api/v1/forecast/ts/{region_id}/{variable}`

---

# EPIC-09 — Network Science Models (Layer 3)

> **Goal:** Model inter-regional hazard contagion, vulnerability propagation,
> and alert prioritisation using graph algorithms — drawing directly from
> GraphAlpha's `systemic_risk`, `network_theory`, and `contagion` categories.
>
> _GraphAlpha reference: `Category {name: 'systemic_risk'}`,
> `Category {name: 'contagion'}`, `Regime {name: 'SystemicStress'}`,
> `Concept {name: 'Network Centrality'}` — all in master.cypher_

---

## FEAT-09-A: Regional Vulnerability PageRank

### User Story 09-A-1
**As a** humanitarian coordinator,
**I want** each region's vulnerability score to account for how connected it is
to other high-risk regions,
**So that** a region that is moderately at-risk but surrounded by crisis regions
is correctly elevated in priority.

#### Model Specification

```
Adapted PageRank for Vulnerability Propagation:

  Graph: G = (V, E)
    V = IGAD regions (admin-level 1, ~150 nodes)
    E = edges weighted by:
        w(i,j) = trade_dependency(i,j) × population_flow(i,j)
                 × border_permeability(i,j)

  PageRank variant (personalised):
    PR(i) = (1-d)/N + d × Σⱼ PR(j) × w(j,i) / Σₖ w(j,k)
    d = 0.85 (damping factor)
    personalisation: seeded by current IPC phase

  Systemic Risk Score:
    SystemicRisk(i) = PR(i) × CurrentRiskScore(i) × VulnerabilityMultiplier(i)

  Maps to GraphAlpha concept:
    PR(i) ≡ "contagion centrality" in systemic risk literature
    Same as interbank network PageRank in master.cypher SystemicStress regime
```

#### Acceptance Criteria
- [ ] `models/network/pagerank_vulnerability.py` using `networkx`
- [ ] Region adjacency graph built from IGAD border data + trade flows (World Bank)
- [ ] PageRank computed weekly, stored as `Region.pagerank_score`
- [ ] `SystemicRisk` score = PageRank × current risk × vulnerability
- [ ] Regions with top-5 systemic risk scores flagged with `SYSTEMICALLY_CRITICAL`
  relationship to a `NetworkRiskAlert` node
- [ ] Network graph visualisation in React (force-directed, nodes sized by PR)

#### Tasks
- [ ] `T-09-A-1-1` `models/network/pagerank_vulnerability.py`
- [ ] `T-09-A-1-2` Region adjacency graph builder from GADM + World Bank data
- [ ] `T-09-A-1-3` Neo4j `Region.pagerank_score` updater
- [ ] `T-09-A-1-4` `NetworkRiskAlert` node writer
- [ ] `T-09-A-1-5` React `NetworkGraph` visualisation (react-force-graph, node size = PR)

---

## FEAT-09-B: Hazard Contagion Cascade Simulation

### User Story 09-B-1
**As a** scenario planner,
**I want** to simulate how a drought in one region cascades to food insecurity
in neighbouring regions over 8 weeks,
**So that** I can identify which region's early intervention breaks the
contagion chain most efficiently.

#### Model Specification

```
SIR-inspired Contagion Model on Region Graph:

  States: Susceptible (S), At-Risk (A), Crisis (C), Recovering (R)
  Transition probabilities learned from historical IPC cascade data:

    P(S→A) = β × (IPC_phase_neighbour / 5) × (1 - road_access_score)
    P(A→C) = γ × current_risk_score × (1 - intervention_coverage)
    P(C→R) = δ × (humanitarian_access_score)

  Simulation: 1,000 Monte Carlo cascade paths, 8-week horizon
  Output per region:
    cascade_probability: P(enters Crisis within 8 weeks given neighbours)
    critical_intervention_node: region whose intervention most reduces cascade P

  Maps to GraphAlpha:
    β ≡ contagion transmission weight (master.cypher systemic_risk category)
    P(S→A) ≡ jump intensity in Jump Diffusion model
    cascade_probability ≡ CVaR at the network level
```

#### Acceptance Criteria
- [ ] `models/network/contagion_cascade.py`
- [ ] 1,000 Monte Carlo cascade paths per week
- [ ] `CascadeSignal {source_region, cascade_probability, critical_node,
  weeks_to_crisis, simulated_at}` stored in Neo4j
- [ ] "Break the chain" recommendation: critical intervention node highlighted
  in React dashboard with `🔗 Chain Breaker` badge
- [ ] FastAPI endpoint: `POST /api/v1/scenarios/cascade` — run on-demand simulation
  with user-specified initial conditions

#### Tasks
- [ ] `T-09-B-1-1` `models/network/contagion_cascade.py`
- [ ] `T-09-B-1-2` Transition probability calibration from historical IPC sequences
- [ ] `T-09-B-1-3` Neo4j `CascadeSignal` writer
- [ ] `T-09-B-1-4` React `CascadeScenarioPanel` with chain-breaker highlight
- [ ] `T-09-B-1-5` On-demand scenario API endpoint

---

## FEAT-09-C: Community Detection — Aid Allocation Clustering

### User Story 09-C-1
**As an** NGO programme officer,
**I want** regions automatically clustered into aid allocation zones based on
their hazard similarity and connectivity,
**So that** aid pre-positioning can be planned at the cluster level rather than
one-region-at-a-time.

#### Model Specification

```
Louvain Community Detection on Hazard Similarity Graph:

  Edge weight w(i,j) = cosine_similarity(
    [SPI_i, NDVI_i, IPC_i, PR_i], [SPI_j, NDVI_j, IPC_j, PR_j]
  ) × geographic_adjacency(i,j)

  Louvain algorithm: maximise modularity Q
  Output: 8–15 communities (clusters) across IGAD

  Cluster risk score: max(member region risk scores) — worst-case basis
  Cluster label: LLM-generated human-readable name
    e.g. "Northern Rift Valley Drought Corridor" or "Somali Coast Food Crisis Belt"
```

#### Acceptance Criteria
- [ ] `models/network/community_detection.py` using `networkx` + `python-louvain`
- [ ] Clusters stored as `HazardCluster` nodes in Neo4j
- [ ] Region → cluster `BELONGS_TO_CLUSTER` relationship
- [ ] Cluster label generated by Groq LLM from member region names + dominant hazard
- [ ] Cluster-level alerts: if cluster risk > 70, single advisory covers all members
- [ ] React: choropleth coloured by cluster (overlay option)

#### Tasks
- [ ] `T-09-C-1-1` `models/network/community_detection.py`
- [ ] `T-09-C-1-2` `HazardCluster` Neo4j nodes + `BELONGS_TO_CLUSTER` rels
- [ ] `T-09-C-1-3` Groq cluster labelling prompt
- [ ] `T-09-C-1-4` Cluster-level alert aggregation service
- [ ] `T-09-C-1-5` React cluster choropleth toggle

---

# EPIC-10 — Bayesian Model Averaging & Kelly Risk Engine (Layer 5)

> **Goal:** Combine outputs from all 8 models (SDE, HMM, Kalman, LSTM, XGBoost,
> CNN, TimeGPT, PageRank) into a single posterior risk score using Bayesian
> Model Averaging — and apply Kelly-fractional prioritisation to rank alerts.
>
> _GraphAlpha direct reference: `Formula {id: 'f_kelly'}` from master.cypher —
> the same Kelly criterion used for trade sizing now used for alert prioritisation._

---

## FEAT-10-A: Bayesian Model Averaging Engine

### User Story 10-A-1
**As a** data scientist,
**I want** all model outputs combined via Bayesian Model Averaging,
**So that** the final risk score reflects the consensus of all models,
weighted by their recent predictive accuracy.

#### Model Specification

```
Bayesian Model Averaging (BMA):

  Models M = {SDE, HMM, LSTM, XGBoost, CNN, TimeGPT, PageRank, VARLiNGAM}
  Each model m produces P(crisis | data, Mₘ)

  BMA posterior:
    P(crisis | data) = Σₘ P(crisis | data, Mₘ) × P(Mₘ | data)

  Model weights (updated weekly via Brier score):
    P(Mₘ | data) ∝ exp(-BrierScore(Mₘ, last_8_weeks))
    Normalised to sum to 1

  Uncertainty quantification:
    Epistemic uncertainty = variance across model predictions
    High epistemic uncertainty → advisory confidence = "Low"
    Low uncertainty + high risk → advisory confidence = "High"

  Implementation: `pymc` for full Bayesian treatment if compute allows,
                  else closed-form BMA with scipy
```

#### Acceptance Criteria
- [ ] `models/ensemble/bma_engine.py`
- [ ] 8 model outputs combined per region per week
- [ ] Model weights updated weekly from `model_performance` PostgreSQL table
- [ ] `BMAScore {posterior_risk, epistemic_uncertainty, model_weights_json,
  computed_at}` stored in Neo4j
- [ ] Confidence level: High / Medium / Low shown in React alert badge
- [ ] Weight history chart in admin panel (recharts StackedBar)

#### Tasks
- [ ] `T-10-A-1-1` `models/ensemble/bma_engine.py`
- [ ] `T-10-A-1-2` Brier score tracker per model per week
- [ ] `T-10-A-1-3` Weight normalisation + update service
- [ ] `T-10-A-1-4` `BMAScore` Neo4j writer
- [ ] `T-10-A-1-5` React `ModelWeightChart` (recharts StackedBarChart)

---

## FEAT-10-B: Kelly Alert Prioritisation

### User Story 10-B-1
**As an** ICPAC operations officer,
**I want** alert dispatch prioritised by a Kelly-fractional score,
**So that** if bandwidth is limited, the alerts with the highest
information-to-noise ratio are sent first.

#### Model Specification

```
Kelly Alert Priority Score (adapted from GraphAlpha f_kelly):

  GraphAlpha Kelly formula: f* = (bp - q) / b
    b = odds received, p = P(win), q = 1-p

  HazardGraph adaptation:
    Priority(alert) = (BMA_risk_score × confidence) - (1 - BMA_risk_score)
                      / BMA_risk_score

  Interpretation:
    High BMA risk + high confidence → high Kelly score → send first
    High BMA risk + low confidence  → moderate Kelly score → send second
    Low risk + high confidence      → low/negative Kelly → do not send

  Epistemic discount:
    Effective_priority = Kelly_score × (1 - epistemic_uncertainty)
```

#### Acceptance Criteria
- [ ] `models/ensemble/kelly_prioritiser.py`
- [ ] Kelly score computed for every pending alert
- [ ] Alert dispatch queue ordered by Kelly score descending
- [ ] Negative Kelly score → alert held pending confirmation
- [ ] React `AlertQueue` shows Kelly score next to each pending alert
- [ ] Admin can override Kelly ordering with justification (logged)

#### Tasks
- [ ] `T-10-B-1-1` `models/ensemble/kelly_prioritiser.py`
- [ ] `T-10-B-1-2` Alert queue ordering service
- [ ] `T-10-B-1-3` React `AlertQueue` table with Kelly score column (shadcn DataTable)
- [ ] `T-10-B-1-4` Admin override endpoint + audit log

---

# EPIC-11 — Quantifaya Brand Integration & Long-Term Platform Vision

> **Goal:** Establish HazardGraph as the first product in the Quantifaya
> Climate Intelligence Suite, with a shared component library, API, and
> brand identity that supports future expansion.

---

## FEAT-11-A: Quantifaya Design System

### User Story 11-A-1
**As a** brand owner,
**I want** HazardGraph to be visually and technically aligned with the
Quantifaya brand,
**So that** it is immediately recognisable as a Quantifaya product when
presented to ICPAC judges and future customers.

#### Acceptance Criteria
- [ ] Raleway font applied globally (400, 600, 700 weights)
- [ ] Colour palette:
  - Primary: `#0F4C81` (Quantifaya deep blue)
  - Accent: `#00C896` (Quantifaya green — same as GraphAlpha)
  - Warning: `#F59E0B` (amber)
  - Danger: `#EF4444` (red)
  - Background: `#0A0F1E` (dark mode default)
- [ ] "Powered by Quantifaya" footer on all pages
- [ ] `quantifaya.vercel.app` linked in app header
- [ ] Favicon: Quantifaya logo SVG
- [ ] shadcn theme config in `components/ui/theme.ts` exports all tokens
- [ ] Shared component: `<QuantifayaHeader />` with nav links to Quantifaya site

#### Tasks
- [ ] `T-11-A-1-1` `tailwind.config.js` — Quantifaya colour tokens
- [ ] `T-11-A-1-2` `components/ui/theme.ts` — shadcn theme overrides
- [ ] `T-11-A-1-3` Google Fonts Raleway import in `index.css`
- [ ] `T-11-A-1-4` `<QuantifayaHeader />` component
- [ ] `T-11-A-1-5` Favicon + meta tags (OG image for social share)

---

## FEAT-11-B: Public API — Quantifaya Climate Intelligence API

### User Story 11-B-1
**As a** third-party developer,
**I want** a documented public API to access HazardGraph's risk scores and
forecasts,
**So that** NGOs and government agencies can integrate Quantifaya's intelligence
into their own systems without using the dashboard.

#### Acceptance Criteria
- [ ] OpenAPI docs at `/docs` (FastAPI auto-generated)
- [ ] Public endpoints (no auth):
  - `GET /api/v1/public/risk/scores` — all region scores (cached)
  - `GET /api/v1/public/forecast/{region_id}` — BMA forecast
- [ ] Rate limited: 100 req/hour per IP (Redis sliding window)
- [ ] API key registration endpoint for higher limits
- [ ] "Quantifaya Climate Intelligence API v1" branding in OpenAPI spec
- [ ] Postman collection exported + linked in README

#### Tasks
- [ ] `T-11-B-1-1` Public router in FastAPI with Redis rate limiter
- [ ] `T-11-B-1-2` OpenAPI metadata: title, description, contact, logo
- [ ] `T-11-B-1-3` API key table in PostgreSQL + key validator middleware
- [ ] `T-11-B-1-4` Postman collection export
- [ ] `T-11-B-1-5` README API section with cURL examples

---

## FEAT-11-C: Long-Term Quantifaya Product Roadmap

> _This section documents post-hackathon expansion — not in scope for July 31
> submission but critical for the brand vision pitch._

```
Phase 1 (Hackathon — July 31):
  HazardGraph MVP — IGAD 11 countries, 8 models, SMS alerts, Neo4j graph

Phase 2 (Q4 2026 — Post-Hackathon):
  • Expand to all 54 African countries
  • Add Conflict data (ACLED API) as a hazard node type
  • USSD interface (Africa's Talking) — feature phone access for pastoralists
  • M-Pesa micro-insurance trigger: if risk > 80, auto-notify insurer partner
  • Arabic + French advisory language support

Phase 3 (2027 — Quantifaya Climate Suite):
  Product 1: HazardGraph (this product) — humanitarian early warning
  Product 2: AgriRisk — crop yield forecasting for smallholder finance
  Product 3: ClimateAlpha — climate-adjusted asset pricing for African equities
             [direct bridge from GraphAlpha financial engineering knowledge graph]
  Product 4: WeatherDesk — B2B API for African climate data consumers

Phase 4 (2028 — Platform):
  • Unified Quantifaya Knowledge Graph: financial + climate nodes connected
    e.g. ENSO event → rainfall anomaly → food price spike →
         East African equities → currency stress → sovereign bond risk
  • Single graph traversal: climate signal → market impact → portfolio hedge
  • This is the unique Quantifaya insight: the two graphs are one graph.
```

---

## Updated Delivery Milestones (6 Days, Prioritised)

| Day | Milestone | Must-Have for Demo | Epics |
|---|---|---|---|
| **1** | Schema + data ingestion + Neo4j seeded | ✅ | 01, 02-A |
| **2** | HMM regime detection + VARLiNGAM causal graph | ✅ | 02-B, 07-B |
| **3** | XGBoost + BMA risk score + choropleth dashboard | ✅ | 08-B, 10-A, 03-B |
| **4** | LLM advisory + Kelly queue + AT sandbox SMS | ✅ | 04, 10-B |
| **5** | PageRank network + LSTM (if time) + feedback loop | ⬛ nice-to-have | 09-A, 08-A, 05 |
| **6** | Quantifaya design system + demo video + submission | ✅ | 11-A |

**Minimum viable demo (if time-constrained):**
Epics 01, 02 (graph only), 03 (risk score), 04 (SMS), 10-A (BMA), 11-A (brand)
= a complete, defensible submission that wins on Technical Depth + AI Innovation.

---

## Complete Model Registry

| ID | Model | Category | Library | Output | Frequency |
|---|---|---|---|---|---|
| M1 | CIR + Jump Diffusion SDE | Stochastic | `scipy`, `numpy` | P(flood/drought 4w) | Weekly |
| M2 | Hidden Markov Model | Statistical | `hmmlearn` | HazardRegime label | Weekly |
| M3 | Kalman Filter | Filtering | `filterpy` | Smoothed SPI/NDVI | Daily |
| M4 | Bidirectional LSTM | Deep Learning | `torch` | P(IPC phase 1-5, 4w) | Weekly |
| M5 | XGBoost + SHAP | ML | `xgboost`, `shap` | P(Crisis 8w) + explanation | Weekly |
| M6 | CNN (NDVI) | Deep Learning | `torch`, `rasterio` | Vegetation stress P | Weekly |
| M7 | Prophet + TimeGPT | Foundation Model | `neuralprophet`, Nixtla | 12w forecast + CI | Weekly |
| M8 | VARLiNGAM | Causal | `lingam` | Causal graph edges | Monthly |
| M9 | PageRank | Network Science | `networkx` | Contagion centrality | Weekly |
| M10 | Louvain Community | Network Science | `python-louvain` | Aid allocation clusters | Monthly |
| M11 | SIR Cascade | Network Science | `networkx` | Contagion probability | Weekly |
| M12 | BMA Engine | Ensemble | `scipy`, `pymc` | Posterior risk score | Weekly |
| M13 | Kelly Prioritiser | Decision Theory | custom | Alert dispatch order | On-demand |

---

_Specification version 2.0 | July 25, 2026_
_Author: Godwin Edgar Opuka | Quantifaya_
_"The same graph that prices volatility can price vulnerability."_
