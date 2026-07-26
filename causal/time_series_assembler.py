"""HazardGraph — Time series assembler for causal discovery.

Pulls RainfallSignal, FoodPriceSignal, and IPCPhaseSignal data from
Neo4j for a given region and assembles a weekly panel DataFrame
ready for VARLiNGAM.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd

from db.neo4j_client import neo4j_client

logger = logging.getLogger(__name__)

MIN_ROWS = 52  # minimum 1 year of weekly data


async def assemble_panel(
    region_id: str,
    lookback_weeks: int = 104,
) -> Optional[pd.DataFrame]:
    """Assemble a weekly panel DataFrame for a region.

    Fetches RainfallSignal, FoodPriceSignal, and IPCPhaseSignal nodes
    from Neo4j, resamples to weekly frequency, merges, and computes
    rolling features.

    Returns:
        DataFrame with columns [date, spi_30d, food_price_pct_change,
        ipc_phase, rainfall_trend_slope] indexed by weekly dates.
        Returns None if fewer than MIN_ROWS rows after cleaning.
    """
    try:
        # 1. Fetch RainfallSignal data
        rainfall_query = """
        MATCH (rs:RainfallSignal {region_id: $region_id})
        RETURN rs.date AS date, rs.spi_30d AS spi_30d
        ORDER BY rs.date ASC
        """
        rainfall_data = await neo4j_client.execute_read(rainfall_query, {"region_id": region_id})

        # 2. Fetch FoodPriceSignal data
        food_query = """
        MATCH (fps:FoodPriceSignal {region_id: $region_id})
        RETURN fps.date AS date, fps.pct_change_30d AS food_price_pct_change
        ORDER BY fps.date ASC
        """
        food_data = await neo4j_client.execute_read(food_query, {"region_id": region_id})

        # 3. Fetch IPCPhaseSignal data
        ipc_query = """
        MATCH (ipc:IPCPhaseSignal {region_id: $region_id})
        RETURN ipc.reference_date AS date, ipc.phase AS ipc_phase
        ORDER BY ipc.reference_date ASC
        """
        ipc_data = await neo4j_client.execute_read(ipc_query, {"region_id": region_id})

        if not rainfall_data and not food_data and not ipc_data:
            logger.warning("No signal data found for region %s", region_id)
            return None

        # 4. Convert to DataFrames
        dfs = []

        if rainfall_data:
            df_r = pd.DataFrame(rainfall_data)
            df_r["date"] = pd.to_datetime(df_r["date"], errors="coerce")
            df_r["spi_30d"] = pd.to_numeric(df_r["spi_30d"], errors="coerce")
            dfs.append(df_r)

        if food_data:
            df_f = pd.DataFrame(food_data)
            df_f["date"] = pd.to_datetime(df_f["date"], errors="coerce")
            df_f["food_price_pct_change"] = pd.to_numeric(df_f["food_price_pct_change"], errors="coerce")
            dfs.append(df_f)

        if ipc_data:
            df_i = pd.DataFrame(ipc_data)
            df_i["date"] = pd.to_datetime(df_i["date"], errors="coerce")
            df_i["ipc_phase"] = pd.to_numeric(df_i["ipc_phase"], errors="coerce")
            dfs.append(df_i)

        # 5. Merge on date (outer join)
        merged = dfs[0]
        for df in dfs[1:]:
            merged = pd.merge(merged, df, on="date", how="outer")

        # 6. Sort by date and set index
        merged = merged.sort_values("date").drop_duplicates(subset="date")
        merged = merged.set_index("date")

        # 7. Resample to weekly frequency (W-MON = weekly, Monday)
        weekly = merged.resample("W-MON").mean()

        # 8. Forward-fill gaps (max 2 weeks)
        weekly = weekly.ffill(limit=2)

        # 9. Drop rows where critical columns are still NaN
        critical_cols = [c for c in ["spi_30d", "food_price_pct_change", "ipc_phase"] if c in weekly.columns]
        if critical_cols:
            weekly = weekly.dropna(subset=critical_cols, how="any")

        # 10. Add rolling slope feature: rainfall_trend_slope
        if "spi_30d" in weekly.columns:
            def _rolling_slope(series: pd.Series) -> float:
                if len(series) < 4:
                    return 0.0
                y = series.values[-4:]
                x = np.arange(4)
                try:
                    slope = np.polyfit(x, y, 1)[0]
                    return float(slope)
                except (np.linalg.LinAlgError, ValueError):
                    return 0.0

            weekly["rainfall_trend_slope"] = (
                weekly["spi_30d"]
                .rolling(window=4, min_periods=4)
                .apply(_rolling_slope, raw=False)
            )

        # 11. Clip SPI to [-3, 3]
        if "spi_30d" in weekly.columns:
            weekly["spi_30d"] = weekly["spi_30d"].clip(-3.0, 3.0)

        # 12. Check minimum row count
        if len(weekly) < MIN_ROWS:
            logger.warning(
                "Insufficient data for region %s: %d rows (need %d)",
                region_id, len(weekly), MIN_ROWS,
            )
            return None

        # 13. Keep only the most recent lookback_weeks
        if len(weekly) > lookback_weeks:
            weekly = weekly.tail(lookback_weeks)

        logger.info(
            "Assembled panel for %s: %d rows, %d columns",
            region_id, len(weekly), len(weekly.columns),
        )
        return weekly

    except Exception as exc:
        logger.error("Failed to assemble panel for region %s: %s", region_id, exc)
        return None