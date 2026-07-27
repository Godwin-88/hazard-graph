"""Test all ingestion modules against test Neo4j container."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestICPACIngestion:
    @pytest.mark.asyncio
    async def test_rss_fetch_writes_forecast_signal(
        self, neo4j_driver, redis_client
    ):
        """Mock ICPAC RSS + Groq, verify ForecastSignal written to Neo4j."""
        mock_rss_response = {
            'entries': [{
                'title': 'Drought alert for Horn of Africa',
                'published': '2026-07-20',
                'summary': 'Severe drought conditions expected in Kenya',
                'link': 'https://icpac.net/test'
            }]
        }
        mock_groq_response = MagicMock()
        mock_groq_response.choices[0].message.content = (
            '{"region":"Kenya","hazard_type":"drought",'
            '"severity":0.8,"forecast_horizon_days":30,"confidence_pct":0.75}'
        )
        with patch('feedparser.parse', return_value=mock_rss_response), \
             patch('groq.AsyncGroq') as mock_groq:
            mock_groq.return_value.chat.completions.create = \
                AsyncMock(return_value=mock_groq_response)
            from ingestion.icpac_rss_fetcher import ICPACRSSFetcher
            fetcher = ICPACRSSFetcher()
            async with neo4j_driver.session() as session:
                count = await fetcher.fetch_and_write(session, redis_client)

        assert count >= 1
        # Verify node exists in Neo4j
        async with neo4j_driver.session() as session:
            result = await session.run(
                'MATCH (f:ForecastSignal) WHERE f.hazard_type=$ht RETURN count(f) as n',
                ht='drought'
            )
            record = await result.single()
            assert record['n'] >= 1

    @pytest.mark.asyncio
    async def test_chirps_writes_rainfall_signal(self, neo4j_driver):
        """Mock rasterio, verify RainfallSignal + SPI computation."""
        import numpy as np
        mock_raster = MagicMock()
        mock_raster.read.return_value = np.full((1, 100, 100), 45.0)
        mock_raster.bounds = MagicMock(
            left=34.0, bottom=-4.7, right=42.0, top=5.0
        )
        mock_raster.crs = MagicMock()
        mock_raster.__enter__ = lambda s: s
        mock_raster.__exit__ = MagicMock(return_value=False)

        with patch('rasterio.open', return_value=mock_raster), \
             patch('httpx.AsyncClient.get') as mock_get:
            mock_get.return_value = AsyncMock()
            mock_get.return_value.content = b'fake_tif_data'
            mock_get.return_value.raise_for_status = MagicMock()
            from ingestion.chirps_fetcher import CHIRPSFetcher
            fetcher = CHIRPSFetcher()
            async with neo4j_driver.session() as session:
                results = await fetcher.fetch_all_regions(session)

        assert 'kenya' in results
        assert -3.0 <= results['kenya']['spi_30d'] <= 3.0

    @pytest.mark.asyncio
    async def test_kalman_smoothing_applied(self, sample_rainfall_series):
        """Verify Kalman smoother reduces noise in SPI series."""
        from models.filtering.kalman import KalmanSmoother
        smoother = KalmanSmoother(process_noise=0.1, measurement_noise=0.5)
        smoothed = smoother.smooth_series(sample_rainfall_series)
        assert len(smoothed) == len(sample_rainfall_series)
        # Smoothed variance must be less than raw variance
        import numpy as np
        raw_var = np.var(sample_rainfall_series)
        smooth_var = np.var(smoothed)
        assert smooth_var < raw_var, (
            f"Kalman smoother increased variance: {smooth_var} > {raw_var}"
        )