"""Tests for new model implementations (M6 CNN, M10 Louvain, M11 SIR)."""

import numpy as np
import pytest


class TestNDVICNN:
    def test_model_output_is_probability(self):
        from models.ml.ndvi_cnn import NDVIAnomalyDetector
        detector = NDVIAnomalyDetector()
        patch = detector._generate_synthetic_patch('kenya', stress_level=0.7)
        p = detector.predict(patch)
        assert 0.0 <= p <= 1.0

    def test_stressed_patch_higher_probability(self):
        from models.ml.ndvi_cnn import NDVIAnomalyDetector
        d = NDVIAnomalyDetector()
        d.train(epochs=5)
        p_stressed = d.predict(
            d._generate_synthetic_patch('kenya', stress_level=0.9)
        )
        p_normal = d.predict(
            d._generate_synthetic_patch('kenya', stress_level=0.1)
        )
        assert p_stressed > p_normal - 0.1

    def test_save_and_load_model(self):
        from models.ml.ndvi_cnn import NDVIAnomalyDetector
        import os
        d = NDVIAnomalyDetector()
        d.train(epochs=3)
        assert os.path.exists('models/saved/ndvi_cnn.pt')
        d2 = NDVIAnomalyDetector()
        assert d2.load()
        assert d2.is_fitted


class TestProphetTimeGPT:
    def test_prophet_fallback_on_empty_key(self):
        from models.ml.timeseries_ensemble import TimeSeriesEnsemble
        import pandas as pd
        dates = pd.date_range('2025-01-01', periods=52, freq='W')
        series = pd.Series(np.random.normal(0, 1, 52), index=dates)
        ensemble = TimeSeriesEnsemble(nixtla_api_key='')
        import asyncio
        fc = asyncio.run(ensemble.forecast(series, 'kenya', 'spi_30d', horizon=4))
        assert len(fc.values) == 4
        assert len(fc.lower_ci) == 4
        assert len(fc.upper_ci) == 4

    def test_forecast_returns_valid_dates(self):
        from models.ml.timeseries_ensemble import TimeSeriesEnsemble
        import pandas as pd
        dates = pd.date_range('2025-01-01', periods=26, freq='W')
        series = pd.Series(np.random.normal(0, 1, 26), index=dates)
        ensemble = TimeSeriesEnsemble(nixtla_api_key='')
        import asyncio
        fc = asyncio.run(ensemble.forecast(series, 'ethiopia', 'food_price_pct', horizon=6))
        assert fc.region_id == 'ethiopia'
        assert fc.variable == 'food_price_pct'
        assert fc.horizon_weeks == 6


class TestLouvainClustering:
    def test_all_regions_assigned_cluster(self):
        from models.network.community_detection import LouvainHazardClustering
        clustering = LouvainHazardClustering()
        regions = ['kenya', 'ethiopia', 'somalia', 'sudan',
                   'south_sudan', 'uganda', 'djibouti', 'eritrea',
                   'tanzania', 'burundi', 'rwanda']
        risk = {r: 50.0 for r in regions}
        regimes = {r: 'Baseline' for r in risk}
        spi = {r: 0.0 for r in risk}
        G = clustering.build_similarity_graph(risk, regimes, spi, {})
        partition = clustering.detect_clusters(G)
        assert len(partition) == 11
        assert all(isinstance(v, int) for v in partition.values())

    def test_similar_regions_cluster_together(self):
        from models.network.community_detection import LouvainHazardClustering
        c = LouvainHazardClustering()
        regions = ['kenya', 'ethiopia', 'somalia', 'sudan',
                   'south_sudan', 'uganda', 'djibouti', 'eritrea',
                   'tanzania', 'burundi', 'rwanda']
        risk = {r: 30.0 for r in regions}
        risk['rwanda'] = 75.0
        risk['burundi'] = 75.0
        regimes = {r: 'Baseline' for r in risk}
        regimes['rwanda'] = 'SevereDrought'
        regimes['burundi'] = 'SevereDrought'
        spi = {r: 0.0 for r in risk}
        G = c.build_similarity_graph(risk, regimes, spi, {})
        partition = c.detect_clusters(G)
        assert partition['rwanda'] == partition['burundi'], (
            "Rwanda and Burundi should cluster together"
        )


class TestSIRCascade:
    def test_cascade_from_high_risk_source(self):
        from models.network.contagion_cascade import SIRCascadeSimulator
        sim = SIRCascadeSimulator()
        risk = {'ethiopia': 90.0, 'kenya': 40.0, 'somalia': 80.0,
                'sudan': 50.0, 'south_sudan': 85.0, 'uganda': 30.0,
                'djibouti': 55.0, 'eritrea': 45.0, 'tanzania': 25.0,
                'burundi': 35.0, 'rwanda': 28.0}
        vm = {r: 1.5 for r in risk}
        result = sim.compute_cascade_result(
            source_region='somalia', risk_scores=risk,
            vulnerability_multipliers=vm, n_paths=200, horizon_weeks=4
        )
        assert result.cascade_probabilities['somalia'] >= 0.90
        assert result.expected_affected_population > 0
        assert result.critical_intervention_node in risk

    def test_p_cascade_source_always_near_one(self):
        from models.network.contagion_cascade import SIRCascadeSimulator
        sim = SIRCascadeSimulator()
        regions = ['kenya', 'ethiopia', 'somalia', 'sudan',
                   'south_sudan', 'uganda', 'djibouti', 'eritrea',
                   'tanzania', 'burundi', 'rwanda']
        risk = {r: 50.0 for r in regions}
        vm = {r: 1.5 for r in risk}
        result = sim.compute_cascade_result(
            'kenya', risk, vm, n_paths=100, horizon_weeks=2
        )
        assert result.cascade_probabilities['kenya'] >= 0.95