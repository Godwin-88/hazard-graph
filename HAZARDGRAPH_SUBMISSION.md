# Hazard Graph

## Project Overview

The Horn of Africa faces recurring drought, flood, and food crises that push millions toward starvation. Early warning systems exist but are fragmented across agencies, buried in static PDF reports, and arrive too late for communities that need them most. Humanitarian responders lack a unified view of risk — they must manually cross-reference rainfall data, food prices, conflict reports, and IPC phases from dozens of separate sources.

Hazard Graph is a real-time, AI-powered early warning and decision-support platform for the 11-country IGAD region. It fuses satellite rainfall data (CHIRPS v3.0), food security classifications (IPC), market prices (WFP DataBridges), climate forecasts (ICPAC), and causal models into a single intelligent knowledge graph. The system automatically detects emerging hazard regimes, computes dynamic risk scores per region, and generates localized SMS alerts in Somali, Amharic, Swahili, Arabic, and English — delivered directly to at-risk communities.

**Intended users:** Humanitarian agencies (WFP, FAO, OCHA), national disaster management authorities, NGO field officers, and smallholder farmers who receive SMS alerts. The system serves 11 countries: Ethiopia, Kenya, Somalia, Sudan, South Sudan, Uganda, Tanzania, Rwanda, Burundi, Djibouti, and Eritrea.

---

## Solution Details

Hazard Graph ingests data from 7+ sources through an automated pipeline. CHIRPS v3.0 rainfall data, ICPAC RSS forecasts, FEWS NET IPC phases, and WFP DataBridges market prices are fetched on schedule and written to a Neo4j knowledge graph. A Hidden Markov Model (hmmlearn) detects hazard regimes — Baseline, Drought Onset, Severe Drought, Flood Watch, Flood Emergency — from SPI-30 rainfall anomalies. Causal relationships between variables are discovered using VARLiNGAM, revealing lagged effects (e.g., rainfall deficit → IPC phase deterioration at 21-day lag).

Five ensemble models — XGBoost, LSTM, CNN, NeuralProphet, and stochastic rainfall SDE — produce forecasts combined via Bayesian Model Averaging. Risk scores are weighted by Kelly Criterion for optimal resource allocation. A deep reinforcement learning agent (PPO with Graph Neural Network policy) recommends intervention strategies by simulating the impact of actions on the graph state.

The backend is Python/FastAPI with async SQLAlchemy (Supabase/PostgreSQL), Neo4j 6.x, and Redis (Upstash). Alerts are generated via Groq LLM and delivered through Africa's Talking SMS API. The React/TypeScript frontend (Vercel) provides a force-directed graph explorer, risk choropleth map, and alert review queue. The system is deployed on Render via Docker and uses Neo4j Aura for the managed graph database.