"""Test risk scoring pipeline."""

import pytest


class TestRiskScoring:
    def test_vulnerability_multiplier_range(self):
        """All 11 countries produce multipliers in valid range."""
        from risk.vulnerability_data import get_all_vulnerability_multipliers
        multipliers = get_all_vulnerability_multipliers()
        assert len(multipliers) == 11
        for country, vm in multipliers.items():
            assert 1.0 <= vm <= 2.5, (
                f"{country} vulnerability multiplier {vm} out of range"
            )

    def test_sde_simulation_probabilities_sum(self):
        """SDE Monte Carlo outputs are valid probabilities."""
        from models.stochastic.rainfall_sde import RainfallSDE
        sde = RainfallSDE()
        result = sde.simulate('kenya', r0=-0.8, n_paths=1000)
        assert 0.0 <= result['p_flood_4w'] <= 1.0
        assert 0.0 <= result['p_drought_4w'] <= 1.0
        assert 0.0 <= result['p_severe_4w'] <= 1.0
        # p_severe <= p_drought (subset)
        assert result['p_severe_4w'] <= result['p_drought_4w'] + 0.01

    def test_sde_drought_signal_when_spi_negative(self):
        """Negative SPI should produce higher drought probability."""
        from models.stochastic.rainfall_sde import RainfallSDE
        sde = RainfallSDE()
        normal = sde.simulate('kenya', r0=0.0, n_paths=2000)
        drought = sde.simulate('kenya', r0=-1.5, n_paths=2000)
        assert drought['p_drought_4w'] > normal['p_drought_4w'], (
            "Drought probability should be higher when SPI is negative"
        )

    def test_bma_weights_sum_to_one(self):
        """BMA model weights must always sum to 1.0."""
        from models.ensemble.bma_engine import BMAEngine
        engine = BMAEngine()
        weights = engine.DEFAULT_WEIGHTS
        total = sum(weights.values())
        assert abs(total - 1.0) < 1e-6, (
            f"BMA weights sum to {total}, expected 1.0"
        )

    def test_kelly_negative_for_low_risk(self):
        """Kelly priority must be negative for low-risk low-confidence alerts."""
        from models.ensemble.kelly_prioritiser import compute_kelly_priority
        from models.ensemble.bma_engine import BMAResult
        low_risk = BMAResult(
            region_id='rwanda',
            posterior_risk=0.15,
            epistemic_uncertainty=0.25,
            confidence='Low',
            model_weights={},
            component_probabilities={}
        )
        kelly = compute_kelly_priority(low_risk)
        assert kelly < 0, (
            f"Kelly should be negative for low-risk region, got {kelly}"
        )

    @pytest.mark.asyncio
    async def test_scores_normalised_to_100(
        self, neo4j_driver, postgres_session
    ):
        """All normalised scores must be in [0, 100]."""
        # Seed minimal signal data
        async with neo4j_driver.session() as s:
            for country in ['kenya', 'ethiopia', 'somalia']:
                await s.run(
                    'MERGE (r:RainfallSignal {id: $id}) '
                    'SET r.spi_30d_smoothed = $spi, r.region_id = $rid',
                    id=f'rs_test_{country}',
                    spi=-0.5 if country == 'kenya' else 0.2,
                    rid=country
                )
        from risk.scoring_service import compute_risk_scores
        async with neo4j_driver.session() as s:
            scores = await compute_risk_scores(s)
        for score in scores:
            assert 0.0 <= score.score <= 100.0, (
                f"{score.region_id} score {score.score} out of range"
            )