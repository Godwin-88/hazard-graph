"""
Feature pipeline for ML models.
Assembles feature matrices from Neo4j graph data
for both LSTM and XGBoost models.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta


class FeaturePipeline:
    """
    Builds feature matrices from Neo4j time-series data.
    Handles missing data, alignment, and normalisation.
    """

    def __init__(self):
        self.region_ids = [
            'kenya', 'ethiopia', 'somalia', 'sudan', 'south_sudan',
            'uganda', 'djibouti', 'eritrea', 'tanzania', 'burundi', 'rwanda'
        ]

    async def assemble_panel(self, neo4j_session, region_id: str,
                             lookback_weeks: int = 104) -> pd.DataFrame | None:
        """
        Assemble weekly panel of all features for a region.
        Returns DataFrame with columns: week_start, spi_30d, ndvi_anomaly,
        food_price_pct, ipc_phase, hmm_regime, sde_p_drought, etc.
        """
        async with neo4j_session as s:
            # Get rainfall signals
            rainfall = await s.run(
                'MATCH (r:RainfallSignal {region_id: $rid}) '
                'RETURN r.date AS date, r.spi_30d AS spi, '
                'r.spi_30d_smoothed AS spi_smoothed, r.anomaly_pct AS anomaly '
                'ORDER BY r.date ASC',
                rid=region_id
            )
            rain_rows = await rainfall.fetch()

            # Get food price signals
            food = await s.run(
                'MATCH (f:FoodPriceSignal {region_id: $rid}) '
                'RETURN f.date AS date, f.price_pct_change AS price_pct '
                'ORDER BY f.date ASC',
                rid=region_id
            )
            food_rows = await food.fetch()

            # Get IPC phases
            ipc = await s.run(
                'MATCH (i:IPCPhaseSignal {region_id: $rid}) '
                'RETURN i.date AS date, i.phase AS phase '
                'ORDER BY i.date ASC',
                rid=region_id
            )
            ipc_rows = await ipc.fetch()

        if not rain_rows:
            return None

        # Build DataFrame from rainfall as base
        records = []
        for row in rain_rows:
            records.append({
                'date': row['date'],
                'spi_30d': row['spi'] or 0.0,
                'spi_30d_smoothed': row['spi_smoothed'] or 0.0,
                'ndvi_anomaly': row['anomaly'] or 0.0,
            })

        df = pd.DataFrame(records)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)

        # Merge food prices
        if food_rows:
            food_df = pd.DataFrame([
                {'date': r['date'], 'food_price_pct': r['price_pct'] or 0.0}
                for r in food_rows
            ])
            food_df['date'] = pd.to_datetime(food_df['date'])
            df = pd.merge_asof(df, food_df, on='date', direction='nearest')

        # Merge IPC phases
        if ipc_rows:
            ipc_df = pd.DataFrame([
                {'date': r['date'], 'ipc_phase': r['phase'] or 1}
                for r in ipc_rows
            ])
            ipc_df['date'] = pd.to_datetime(ipc_df['date'])
            df = pd.merge_asof(df, ipc_df, on='date', direction='nearest')

        # Fill missing values
        df['food_price_pct'] = df.get('food_price_pct', 0.0).fillna(0.0)
        df['ipc_phase'] = df.get('ipc_phase', 1).fillna(1).astype(int)

        # Compute derived features
        df['rainfall_trend_slope'] = df['spi_30d'].diff().fillna(0.0)
        df['spi_90d'] = df['spi_30d'].rolling(13, min_periods=1).mean()

        return df.tail(lookback_weeks)