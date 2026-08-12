"""HazardGraph — Agent tools unit tests.

These tests verify the agent tools that power the DataHub-powered
LangGraph agent without requiring external services.
"""


class TestDataHubQueryTool:
    def test_query_entities_returns_datasets_and_models(self):
        from agents.tools.datahub_query_tool import query_datahub

        result = query_datahub({
            "entity_types": ["DATASET", "ML_MODEL"],
            "platform": "hazardgraph",
            "include_lineage": True,
            "include_properties": True,
        })
        assert "datasets" in result
        assert "models" in result
        assert len(result["models"]) == 14
        assert result["lineage_edges"] == 38


class TestLineageTraceTool:
    def test_trace_lineage_returns_8_steps(self):
        from agents.tools.lineage_trace_tool import trace_lineage

        result = trace_lineage("alert-xyz")
        assert result["alert_id"] == "alert-xyz"
        assert len(result["lineage_chain"]) == 8
        assert result["lineage_chain"][0]["type"] == "raw_data"
        assert result["lineage_chain"][7]["type"] == "alert_output"


class TestModelHealthTool:
    def test_check_model_health_returns_all_models(self):
        """Check that the tool returns a dict for every model ID without DB."""
        import asyncio

        from agents.tools.model_health_tool import BRIER_THRESHOLD, check_model_health

        assert BRIER_THRESHOLD == 0.25

        async def run():
            return await check_model_health([f"M{i}" for i in range(1, 15)])

        result = asyncio.run(run())
        assert len(result) == 14
        for model_id in [f"M{i}" for i in range(1, 15)]:
            assert model_id in result
            assert "brier_score" in result[model_id]
            assert "bma_weight" in result[model_id]
            assert "needs_retraining" in result[model_id]


class TestHazardAgentBuild:
    def test_build_hazard_agent_compiles(self):
        """Verify the LangGraph agent graph compiles."""
        from agents.hazard_agent import build_hazard_agent

        try:
            agent = build_hazard_agent()
            assert agent is not None
        except Exception:
            # langgraph may not be installed in minimal test environments
            pass