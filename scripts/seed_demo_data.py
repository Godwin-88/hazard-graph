"""
Populates databases with realistic demo data so the app
looks credible when opened cold for the demo video.

Run: python scripts/seed_demo_data.py
"""

import asyncio
import sys
import os
import datetime
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from dotenv import load_dotenv
load_dotenv()


async def seed():
    from db.neo4j_client import get_driver
    from db.postgres_client import get_engine
    from sqlalchemy.ext.asyncio import AsyncSession
    from models.postgres.base import Base

    driver = await get_driver()
    engine = get_engine()

    print("Creating PostgreSQL tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    print("Seeding Neo4j schema...")
    async with driver.session() as session:
        migration_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'migrations', '001_schema.cypher'
        )
        with open(migration_path) as f:
            migration = f.read()
        for stmt in migration.split(';'):
            stmt = stmt.strip()
            if stmt:
                try:
                    await session.run(stmt)
                except Exception as e:
                    if 'already exists' not in str(e).lower():
                        print(f"  Warning: {e}")

    print("Seeding realistic risk signals...")
    # Seed data representing July 2026 Horn of Africa situation
    demo_signals = [
        # Kenya: drought onset
        {'region': 'kenya', 'spi': -1.2, 'regime': 'DroughtOnset',
         'risk': 67.3, 'ipc': 3, 'food_pct': 0.28},
        # Ethiopia: severe drought
        {'region': 'ethiopia', 'spi': -1.8, 'regime': 'SevereDrought',
         'risk': 82.1, 'ipc': 4, 'food_pct': 0.45},
        # Somalia: severe drought
        {'region': 'somalia', 'spi': -2.1, 'regime': 'SevereDrought',
         'risk': 89.4, 'ipc': 4, 'food_pct': 0.52},
        # Sudan: drought onset
        {'region': 'sudan', 'spi': -0.9, 'regime': 'DroughtOnset',
         'risk': 71.2, 'ipc': 3, 'food_pct': 0.35},
        # South Sudan: severe drought
        {'region': 'south_sudan', 'spi': -1.5, 'regime': 'SevereDrought',
         'risk': 91.7, 'ipc': 4, 'food_pct': 0.60},
        # Uganda: baseline
        {'region': 'uganda', 'spi': 0.2, 'regime': 'Baseline',
         'risk': 32.1, 'ipc': 2, 'food_pct': 0.08},
        # Tanzania: flood watch
        {'region': 'tanzania', 'spi': 1.1, 'regime': 'FloodWatch',
         'risk': 44.8, 'ipc': 2, 'food_pct': 0.12},
        # Rwanda: baseline
        {'region': 'rwanda', 'spi': 0.1, 'regime': 'Baseline',
         'risk': 28.3, 'ipc': 1, 'food_pct': 0.05},
        # Burundi: baseline
        {'region': 'burundi', 'spi': -0.3, 'regime': 'Baseline',
         'risk': 35.6, 'ipc': 2, 'food_pct': 0.11},
        # Djibouti: drought onset
        {'region': 'djibouti', 'spi': -1.0, 'regime': 'DroughtOnset',
         'risk': 58.9, 'ipc': 3, 'food_pct': 0.22},
        # Eritrea: drought onset
        {'region': 'eritrea', 'spi': -0.8, 'regime': 'DroughtOnset',
         'risk': 62.4, 'ipc': 3, 'food_pct': 0.30},
    ]

    async with driver.session() as session:
        for sig in demo_signals:
            # RainfallSignal
            await session.run(
                'MERGE (r:RainfallSignal {id: $id}) '
                'SET r.spi_30d = $spi, r.spi_30d_smoothed = $spi_s, '
                '    r.anomaly_pct = $anom, r.region_id = $rid, '
                '    r.date = $date, r.dekad = 2 '
                'WITH r MATCH (reg:Region {id: $rid}) '
                'MERGE (r)-[:MEASURED_IN]->(reg)',
                id=f'rs_demo_{sig["region"]}',
                spi=sig['spi'],
                spi_s=sig['spi'] * 0.92,
                anom=sig['spi'] / 3.0,
                rid=sig['region'],
                date=datetime.date.today().isoformat()
            )
            # Update region risk score + regime
            await session.run(
                'MATCH (reg:Region {id: $rid}) '
                'SET reg.current_risk_score = $score, '
                '    reg.current_regime = $regime '
                'WITH reg '
                'MATCH (h:HazardRegime {name: $regime}) '
                'MERGE (reg)-[:IN_REGIME]->(h)',
                rid=sig['region'],
                score=sig['risk'],
                regime=sig['regime']
            )
            # Seed 2 causal edges per high-risk region
            if sig['risk'] > 60:
                await session.run(
                    'MERGE (e:CausalEdge {id: $id}) '
                    'SET e.source_variable = "spi_30d", '
                    '    e.target_variable = "ipc_phase", '
                    '    e.weight = $w, e.lag_days = 21, '
                    '    e.method = "VARLiNGAM", e.p_value = 0.02, '
                    '    e.region_id = $rid, e.active = true, '
                    '    e.discovered_at = $now',
                    id=f'ce_demo_{sig["region"]}_spi_ipc',
                    w=min(0.95, sig['risk'] / 100.0 + 0.2),
                    rid=sig['region'],
                    now=datetime.datetime.utcnow().isoformat()
                )

    print("Seeding demo alerts...")
    async with AsyncSession(engine) as pg:
        from models.postgres.alerts import Alert
        from sqlalchemy import insert, select

        # Check if alerts already exist
        existing = await pg.execute(
            select(Alert).where(Alert.region_id.in_(
                ['somalia', 'south_sudan', 'ethiopia']
            ))
        )
        if not existing.scalars().first():
            for region, msg in [
                ('somalia',
                 'Vuna chakula kilichobaki wiki hii. Mvua haitarajiwi '
                 'kwa miezi 2 ijayo.'),
                ('south_sudan',
                 'Move livestock to northern water points before end of '
                 'this week.'),
                ('ethiopia',
                 'Sehemu ya kaskazini: hifadhi mbegu kwa msimu ujao. '
                 'Hali mbaya inatarajiwa.'),
            ]:
                region_idx = [
                    'kenya', 'ethiopia', 'somalia', 'sudan', 'south_sudan',
                    'uganda', 'tanzania', 'rwanda', 'burundi', 'djibouti',
                    'eritrea'
                ].index(region)
                pg.add(Alert(
                    region_id=region,
                    language='swahili' if region != 'south_sudan' else 'english',
                    message_text=msg,
                    risk_score_at_trigger=demo_signals[region_idx]['risk'],
                    kelly_priority=0.55,
                    status='pending',
                    generated_at=datetime.datetime.utcnow(),
                    confidence='High'
                ))
            await pg.commit()
            print("  3 pending alerts seeded.")
        else:
            print("  Alerts already exist, skipping.")

    print("\n✅ Demo data seeded successfully.")
    print("   Somalia, South Sudan, Ethiopia showing high risk (>80)")
    print("   3 pending alerts ready for approval demo")
    print("   Causal edges written for high-risk regions")

    await driver.close()

if __name__ == '__main__':
    asyncio.run(seed())