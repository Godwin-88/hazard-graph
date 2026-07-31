"""
Populates databases with realistic demo data so the app
looks credible when opened cold for the demo video.

Usage:
  # From inside the Docker container:
  docker compose exec app python scripts/seed_demo_data.py

  # Or from host if dependencies are installed:
  cd /home/ed/projects/hazardgraph && python scripts/seed_demo_data.py
"""

import asyncio
import sys
import os
import datetime
import uuid

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Load .env (if running outside Docker)
from dotenv import load_dotenv
load_dotenv()


async def run_migration(neo4j_session):
    """Run the 001_schema.cypher migration file."""
    migration_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'migrations', '001_schema.cypher'
    )
    with open(migration_path) as f:
        migration = f.read()

    for stmt in migration.split(';'):
        stmt = stmt.strip()
        if not stmt or stmt.startswith('//') or stmt.startswith('println'):
            continue
        try:
            await neo4j_session.run(stmt)
        except Exception as e:
            if 'already exists' not in str(e).lower():
                print(f"  Migration warning: {e}")


async def seed_neo4j(neo4j_session):
    """Seed realistic risk signals into Neo4j."""
    # Realistic demo data representing July 2026 Horn of Africa situation
    demo_signals = [
        # Kenya: drought onset
        {'region': 'region_kenya', 'spi': -1.2, 'regime': 'DroughtOnset',
         'risk': 67.3, 'ipc': 3, 'food_pct': 0.28},
        # Ethiopia: severe drought
        {'region': 'region_ethiopia', 'spi': -1.8, 'regime': 'SevereDrought',
         'risk': 82.1, 'ipc': 4, 'food_pct': 0.45},
        # Somalia: severe drought
        {'region': 'region_somalia', 'spi': -2.1, 'regime': 'SevereDrought',
         'risk': 89.4, 'ipc': 4, 'food_pct': 0.52},
        # Sudan: drought onset
        {'region': 'region_sudan', 'spi': -0.9, 'regime': 'DroughtOnset',
         'risk': 71.2, 'ipc': 3, 'food_pct': 0.35},
        # South Sudan: severe drought
        {'region': 'region_south_sudan', 'spi': -1.5, 'regime': 'SevereDrought',
         'risk': 91.7, 'ipc': 4, 'food_pct': 0.60},
        # Uganda: baseline
        {'region': 'region_uganda', 'spi': 0.2, 'regime': 'Baseline',
         'risk': 32.1, 'ipc': 2, 'food_pct': 0.08},
        # Tanzania: flood watch
        {'region': 'region_tanzania', 'spi': 1.1, 'regime': 'FloodWatch',
         'risk': 44.8, 'ipc': 2, 'food_pct': 0.12},
        # Rwanda: baseline
        {'region': 'region_rwanda', 'spi': 0.1, 'regime': 'Baseline',
         'risk': 28.3, 'ipc': 1, 'food_pct': 0.05},
        # Burundi: baseline
        {'region': 'region_burundi', 'spi': -0.3, 'regime': 'Baseline',
         'risk': 35.6, 'ipc': 2, 'food_pct': 0.11},
        # Djibouti: drought onset
        {'region': 'region_djibouti', 'spi': -1.0, 'regime': 'DroughtOnset',
         'risk': 58.9, 'ipc': 3, 'food_pct': 0.22},
        # Eritrea: drought onset
        {'region': 'region_eritrea', 'spi': -0.8, 'regime': 'DroughtOnset',
         'risk': 62.4, 'ipc': 3, 'food_pct': 0.30},
    ]

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    for sig in demo_signals:
        rid = sig['region']

        # 1. Create RainfallSignal node
        await neo4j_session.run(
            """MERGE (rs:RainfallSignal {id: $id})
               SET rs.spi_30d = $spi,
                   rs.spi_30d_smoothed = $spi_s,
                   rs.anomaly_pct = $anom,
                   rs.region_id = $rid,
                   rs.date = $date,
                   rs.dekad = 2
               WITH rs
               MATCH (reg:Region {id: $rid})
               MERGE (rs)-[:MEASURED_IN]->(reg)""",
            id=f'rs_demo_{rid}',
            spi=sig['spi'],
            spi_s=sig['spi'] * 0.92,
            anom=sig['spi'] / 3.0,
            rid=rid,
            date=datetime.date.today().isoformat()
        )

        # 2. Update region risk score + regime
        await neo4j_session.run(
            """MATCH (reg:Region {id: $rid})
               SET reg.current_risk_score = $score,
                   reg.current_regime = $regime
               WITH reg
               MATCH (hr:HazardRegime {name: $regime})
               MERGE (reg)-[:IN_REGIME]->(hr)""",
            rid=rid,
            score=sig['risk'],
            regime=sig['regime']
        )

        # 3. Seed CausalEdge for high-risk regions
        if sig['risk'] > 60:
            await neo4j_session.run(
                """MERGE (ce:CausalEdge {id: $id})
                   SET ce.source_variable = 'spi_30d',
                       ce.target_variable = 'ipc_phase',
                       ce.weight = $w,
                       ce.lag_days = 21,
                       ce.method = 'VARLiNGAM',
                       ce.p_value = 0.02,
                       ce.region_id = $rid,
                       ce.active = true,
                       ce.discovered_at = $now""",
                id=f'ce_demo_{rid}_spi_ipc',
                w=min(0.95, sig['risk'] / 100.0 + 0.2),
                rid=rid,
                now=now
            )

    print(f"  Seeded {len(demo_signals)} regions with rainfall signals + risk scores + causal edges")


async def seed_postgres(postgres_session):
    """Seed demo alerts into PostgreSQL."""
    from models.postgres.alerts import Alert
    from sqlalchemy import select

    # Check if alerts already exist
    existing = await postgres_session.execute(
        select(Alert).where(Alert.region_id.in_(
            ['region_somalia', 'region_south_sudan', 'region_ethiopia']
        ))
    )
    if existing.scalars().first():
        print("  Alerts already exist, skipping.")
        return

    demo_alerts = [
        {
            'region_id': 'region_somalia',
            'language': 'somali',
            'message_text': (
                'Vuna chakula kilichobaki wiki hii. Mvua haitarajiwi '
                'kwa miezi 2 ijayo. Tafuta msaada wa chakula kituo cha karibu.'
            ),
            'risk_score': 89.4,
            'kelly_priority': 0.85,
            'status': 'pending',
        },
        {
            'region_id': 'region_south_sudan',
            'language': 'english',
            'message_text': (
                'Move livestock to northern water points before end of '
                'this week. Severe drought expected to worsen. '
                'Humanitarian aid available at distribution centres.'
            ),
            'risk_score': 91.7,
            'kelly_priority': 0.78,
            'status': 'pending',
        },
        {
            'region_id': 'region_ethiopia',
            'language': 'amharic',
            'message_text': (
                'Sehemu ya kaskazini: hifadhi mbegu kwa msimu ujao. '
                'Hali mbaya ya ukame inatarajiwa. Pata maji kutoka '
                'vituo vya usambazaji.'
            ),
            'risk_score': 82.1,
            'kelly_priority': 0.72,
            'status': 'pending',
        },
        {
            'region_id': 'region_kenya',
            'language': 'swahili',
            'message_text': (
                'Punguza matumizi ya maji wiki hii. Msimu wa mvua '
                'umekawia. Tafuta huduma za mifugo katika eneo lako.'
            ),
            'risk_score': 67.3,
            'kelly_priority': 0.55,
            'status': 'pending',
        },
        {
            'region_id': 'region_sudan',
            'language': 'arabic',
            'message_text': (
                'Early warning: monitor river levels. Flood risk '
                'elevated after recent rains. Move to higher ground if needed.'
            ),
            'risk_score': 71.2,
            'kelly_priority': 0.60,
            'status': 'pending',
        },
    ]

    for a in demo_alerts:
        postgres_session.add(Alert(
            region_id=a['region_id'],
            language=a['language'],
            message_text=a['message_text'],
            risk_score_at_trigger=a['risk_score'],
            kelly_priority=a['kelly_priority'],
            status=a['status'],
            generated_at=datetime.datetime.now(datetime.timezone.utc),
        ))

    await postgres_session.commit()
    print(f"  Seeded {len(demo_alerts)} pending alerts")


async def seed():
    """Main seed routine."""
    from db.neo4j_client import neo4j_client
    from db.postgres_client import async_session_factory, create_all_tables

    # 1. Connect Neo4j
    print("Connecting to Neo4j...")
    await neo4j_client.connect()
    print("  Connected.")

    # 2. Create PostgreSQL tables
    print("Creating PostgreSQL tables...")
    await create_all_tables()
    print("  Done.")

    # 3. Run Neo4j migration
    print("Running Neo4j schema migration...")
    async with neo4j_client.get_session() as session:
        await run_migration(session)
    print("  Migration complete.")

    # 4. Seed Neo4j data
    print("Seeding Neo4j risk signals...")
    async with neo4j_client.get_session() as session:
        await seed_neo4j(session)
    print("  Done.")

    # 5. Seed PostgreSQL data
    print("Seeding PostgreSQL alerts...")
    async with async_session_factory() as pg_session:
        await seed_postgres(pg_session)
    print("  Done.")

    # 6. Close connections
    await neo4j_client.close()

    print()
    print("✅ Demo data seeded successfully!")
    print("   Somalia, South Sudan, Ethiopia showing high risk (>80)")
    print("   Causal edges written for high-risk regions")
    print("   5 pending alerts ready for approval demo")
    print()
    print("   Refresh the dashboard at http://localhost:8000")
    print("   Login: admin / HazardGraph2026!")
    print()


if __name__ == '__main__':
    asyncio.run(seed())