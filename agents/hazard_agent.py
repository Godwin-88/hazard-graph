"""HazardGraph — LangGraph Agent powered by DataHub metadata.

This agent reads HazardGraph's metadata from DataHub via the MCP bridge
before taking any action. It can:

1. Answer "why was this alert dispatched?" by tracing lineage
2. Check whether upstream data is fresh before trusting model outputs
3. Identify which models are underperforming (high Brier score) and flag them
4. Explain the BMA weight distribution in plain English
5. Recommend which regions need immediate attention based on multi-model consensus

The agent writes observations back to DataHub:
- Freshness warnings when upstream data is stale
- Data quality assertions when model outputs are anomalous
- Usage lineage when it reads a dataset or model
"""

import logging
from typing import TypedDict, Optional, List

logger = logging.getLogger(__name__)


class HazardAgentState(TypedDict):
    query: str
    region: Optional[str]
    alert_id: Optional[str]
    datahub_context: Optional[dict]
    lineage_result: Optional[dict]
    freshness_result: Optional[dict]
    model_health: Optional[dict]
    risk_scores: Optional[dict]
    response: Optional[str]
    errors: List[str]


async def fetch_datahub_context(state: HazardAgentState) -> HazardAgentState:
    """Step 1: Read DataHub for metadata context before answering.

    This is the core DataHub integration — every response is grounded
    in the current metadata state of the pipeline.
    """
    from agents.tools.datahub_query_tool import query_datahub

    context = query_datahub({
        "entity_types": ["DATASET", "ML_MODEL"],
        "platform": "hazardgraph",
        "include_lineage": True,
        "include_properties": True,
    })
    state["datahub_context"] = context
    return state


async def check_pipeline_freshness(state: HazardAgentState) -> HazardAgentState:
    """Step 2: Check whether upstream datasets are fresh.

    If CHIRPS or MODIS data is stale, flag all downstream model outputs
    as unreliable. Write a DataHub data quality assertion if staleness
    is detected.
    """
    from agents.tools.freshness_check_tool import check_freshness

    freshness = await check_freshness([
        "chirps_spi_horn_of_africa",
        "modis_ndvi_horn_of_africa",
        "wfp_food_prices_igad",
    ])
    state["freshness_result"] = freshness
    return state


async def assess_model_health(state: HazardAgentState) -> HazardAgentState:
    """Step 3: Check model Brier scores and BMA weights from DataHub.

    Flag any model with Brier score > 0.25 as underperforming.
    Write back to DataHub: tag model as 'needs_retraining'.
    """
    from agents.tools.model_health_tool import check_model_health

    health = await check_model_health(model_ids=[
        "M1", "M2", "M3", "M4", "M5", "M6",
        "M7", "M8", "M9", "M10", "M11", "M12", "M13", "M14",
    ])
    state["model_health"] = health
    return state


async def trace_alert_provenance(state: HazardAgentState) -> HazardAgentState:
    """Step 4 (conditional): If query is about a specific alert,
    trace its complete provenance chain from DataHub lineage.
    """
    if state.get("alert_id"):
        from agents.tools.lineage_trace_tool import trace_lineage

        state["lineage_result"] = trace_lineage(state["alert_id"])
    return state


async def generate_response(state: HazardAgentState) -> HazardAgentState:
    """Step 5: Generate response grounded in DataHub context.

    The LLM only asserts facts that are backed by DataHub metadata.
    Any claim not in the metadata context is prefixed: [UNVERIFIED]
    """
    from config.settings import settings
    from groq import AsyncGroq

    context_block = f"""
DATAHUB PIPELINE CONTEXT:
{state.get('datahub_context', {})}

FRESHNESS STATUS:
{state.get('freshness_result', {})}

MODEL HEALTH (Brier Scores + BMA Weights):
{state.get('model_health', {})}

LINEAGE TRACE:
{state.get('lineage_result', 'Not requested')}
"""

    from agents.prompts.hazard_agent_system import SYSTEM_PROMPT

    if not settings.groq_api_key:
        state["response"] = (
            "[UNVERIFIED] GROQ_API_KEY is not configured. "
            "Cannot generate a grounded LLM response. "
            f"The DataHub context gathered was: {context_block[:2000]}"
        )
        return state

    try:
        client = AsyncGroq(api_key=settings.groq_api_key)
        chat_response = await client.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"""
CONTEXT FROM DATAHUB:
{context_block}

USER QUERY: {state['query']}

Instructions:
- Ground every factual claim in the DataHub context above
- If a fact is not in the context, prefix it with [UNVERIFIED]
- Be specific about model IDs, Brier scores, BMA weights, and data timestamps
- If any data is stale or any model is underperforming, say so clearly
"""},
            ],
            temperature=0.1,
            max_tokens=1000,
        )
        state["response"] = chat_response.choices[0].message.content
    except Exception as exc:
        logger.error("Groq agent response failed: %s", exc)
        state["response"] = (
            f"[ERROR] LLM call failed: {exc}\n\n"
            f"DataHub context gathered (partial): {str(context_block)[:1500]}"
        )
    return state


def build_hazard_agent():
    """Build and compile the HazardGraph LangGraph agent."""
    from langgraph.graph import StateGraph, END

    graph = StateGraph(HazardAgentState)

    graph.add_node("fetch_context", fetch_datahub_context)
    graph.add_node("check_freshness", check_pipeline_freshness)
    graph.add_node("assess_model_health", assess_model_health)
    graph.add_node("trace_lineage", trace_alert_provenance)
    graph.add_node("generate", generate_response)

    graph.set_entry_point("fetch_context")
    graph.add_edge("fetch_context", "check_freshness")
    graph.add_edge("check_freshness", "assess_model_health")
    graph.add_edge("assess_model_health", "trace_lineage")
    graph.add_edge("trace_lineage", "generate")
    graph.add_edge("generate", END)

    # Try to add a checkpointing memory (optional — fails gracefully in tests)
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver

        checkpointer = SqliteSaver.from_conn_string("/tmp/hazard_agent.db")
        return graph.compile(checkpointer=checkpointer)
    except Exception as exc:
        logger.warning("Checkpointing unavailable, compiling without memory: %s", exc)
        return graph.compile()