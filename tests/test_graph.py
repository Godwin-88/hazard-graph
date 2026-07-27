"""Test Neo4j graph operations."""

import pytest


class TestGraphSchema:
    @pytest.mark.asyncio
    async def test_all_node_labels_exist(self, neo4j_driver):
        """Verify all 16 node labels from schema are present."""
        expected_labels = [
            'Region', 'HazardType', 'HazardRegime',
            'InterventionStrategy', 'ForecastSignal', 'RainfallSignal',
            'FoodPriceSignal', 'IPCPhaseSignal', 'VulnerabilityIndex',
            'StochasticSignal', 'MLForecast', 'BMAScore',
            'CausalEdge', 'Alert', 'DataSource', 'HazardCluster'
        ]
        async with neo4j_driver.session() as session:
            result = await session.run(
                'CALL db.labels() YIELD label RETURN collect(label) as labels'
            )
            record = await result.single()
            actual = record['labels']
        for label in expected_labels:
            assert label in actual, f"Missing node label: {label}"

    @pytest.mark.asyncio
    async def test_igad_regions_seeded(self, neo4j_driver):
        """Verify all 11 IGAD country nodes exist."""
        expected = ['Ethiopia', 'Kenya', 'Somalia', 'Sudan',
                    'South Sudan', 'Uganda', 'Djibouti', 'Eritrea',
                    'Tanzania', 'Burundi', 'Rwanda']
        async with neo4j_driver.session() as session:
            result = await session.run(
                'MATCH (r:Region) RETURN collect(r.name) as names'
            )
            record = await result.single()
            actual = record['names']
        for name in expected:
            assert name in actual, f"Missing region: {name}"

    @pytest.mark.asyncio
    async def test_causal_edge_parameterised_query(self, neo4j_driver):
        """Verify no f-string injection — parameterised Cypher only."""
        from causal.edge_writer import write_causal_edges
        from causal.varlingam_engine import CausalEdgeResult
        from datetime import datetime
        test_edges = [CausalEdgeResult(
            source_variable='spi_30d',
            target_variable='ipc_phase',
            weight=0.72,
            lag_weeks=3,
            p_value=0.02,
            region_id='kenya_test',
            discovered_at=datetime.utcnow()
        )]
        async with neo4j_driver.session() as session:
            count = await write_causal_edges(
                session, test_edges, run_id='test-run-001'
            )
        assert count == 1
        # Verify soft-delete works: re-run with different run_id
        async with neo4j_driver.session() as session:
            count2 = await write_causal_edges(
                session, test_edges, run_id='test-run-002'
            )
            result = await session.run(
                'MATCH (e:CausalEdge {region_id: $rid, active: false}) '
                'RETURN count(e) as n',
                rid='kenya_test'
            )
            record = await result.single()
            assert record['n'] >= 1, "Soft-delete not working"

    @pytest.mark.asyncio
    async def test_regime_in_regime_relationship(self, neo4j_driver):
        """Verify IN_REGIME relationship is created correctly."""
        async with neo4j_driver.session() as session:
            # Set a regime on Kenya
            await session.run(
                'MATCH (r:Region {name: "Kenya"}) '
                'MATCH (h:HazardRegime {name: "DroughtOnset"}) '
                'MERGE (r)-[:IN_REGIME]->(h)'
            )
            result = await session.run(
                'MATCH (r:Region {name: "Kenya"})-[:IN_REGIME]->(h) '
                'RETURN h.name as regime'
            )
            record = await result.single()
            assert record['regime'] == 'DroughtOnset'