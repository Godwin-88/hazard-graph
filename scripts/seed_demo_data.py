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


def _regime_id(regime_name: str) -> str:
    """Map a demo regime label to its canonical HazardRegime node id.

    The seed uses camelCase labels like 'SevereDrought' in current_regime,
    but the migration stores HazardRegime nodes keyed by snake-case ids
    like 'regime_severe_drought'. This matches them correctly.
    """
    mapping = {
        "Baseline": "regime_baseline",
        "DroughtOnset": "regime_drought_onset",
        "SevereDrought": "regime_severe_drought",
        "FloodWatch": "regime_flood_watch",
        "FloodEmergency": "regime_flood_emergency",
    }
    return mapping.get(str(regime_name).strip(), f"regime_{str(regime_name).strip().lower()}")


async def register_demo_posteriors(redis_session):
    """Seed realistic regime posteriors into Redis for the Regime Map.

    The HMM updater may not populate Redis on a fresh environment, so the
    Regime Map previously fell back to a flat 'Baseline 0.5' for every
    region. Seeding here gives each region a posterior centred on its
    actual demo regime, so the map renders correctly on first load.
    """
    import json as _json

    default_posteriors = {
        "Baseline":       {"Baseline": 0.78, "DroughtOnset": 0.10, "SevereDrought": 0.04, "FloodWatch": 0.05, "FloodEmergency": 0.03},
        "DroughtOnset":   {"Baseline": 0.15, "DroughtOnset": 0.62, "SevereDrought": 0.14, "FloodWatch": 0.05, "FloodEmergency": 0.04},
        "SevereDrought":  {"Baseline": 0.05, "DroughtOnset": 0.18, "SevereDrought": 0.68, "FloodWatch": 0.05, "FloodEmergency": 0.04},
        "FloodWatch":     {"Baseline": 0.14, "DroughtOnset": 0.05, "SevereDrought": 0.04, "FloodWatch": 0.62, "FloodEmergency": 0.15},
        "FloodEmergency": {"Baseline": 0.05, "DroughtOnset": 0.04, "SevereDrought": 0.03, "FloodWatch": 0.18, "FloodEmergency": 0.70},
    }

    demo_regimes = {
        'region_kenya': 'DroughtOnset',
        'region_ethiopia': 'SevereDrought',
        'region_somalia': 'SevereDrought',
        'region_sudan': 'DroughtOnset',
        'region_south_sudan': 'SevereDrought',
        'region_uganda': 'Baseline',
        'region_tanzania': 'FloodWatch',
        'region_rwanda': 'Baseline',
        'region_burundi': 'Baseline',
        'region_djibouti': 'DroughtOnset',
        'region_eritrea': 'DroughtOnset',
    }

    count = 0
    for region_id, regime in demo_regimes.items():
        key = f"regime_posteriors:{region_id}"
        payload = _json.dumps({
            "regime": regime,
            "posteriors": default_posteriors.get(regime, default_posteriors["Baseline"]),
        })
        try:
            await redis_session.set(key, payload, ttl=3600)
            count += 1
        except Exception as exc:
            print(f"  Warning: failed to seed posteriors for {region_id}: {exc}")
    print(f"  Seeded posteriors for {count} regions into Redis")


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


async def seed_historical_signals(neo4j_session):
    """Backfill ~2 years (104 weeks) of signal history per region.

    This is what makes assemble_panel() return 52+ rows so the HMM,
    VARLiNGAM and risk-scoring stages have real time-series to work
    with. Creates RainfallSignal, FoodPriceSignal, IPCPhaseSignal and
    StochasticSignal nodes with weekly dates linked via MEASURED_IN.
    """
    regions = [
        ('region_somalia', 'SOM', -2.0, 0.85, 4),
        ('region_south_sudan', 'SSD', -1.6, 0.78, 4),
        ('region_ethiopia', 'ETH', -1.5, 0.72, 4),
        ('region_sudan', 'SDN', -0.9, 0.60, 3),
        ('region_kenya', 'KEN', -1.1, 0.55, 3),
        ('region_djibouti', 'DJI', -0.7, 0.40, 3),
        ('region_eritrea', 'ERI', -0.6, 0.45, 3),
        ('region_uganda', 'UGA', 0.4, 0.20, 2),
        ('region_tanzania', 'TZA', 0.6, 0.30, 2),
        ('region_rwanda', 'RWA', 0.3, 0.15, 2),
        ('region_burundi', 'BDI', -0.2, 0.35, 2),
    ]

    now = datetime.datetime.now(datetime.timezone.utc)
    total = 0
    for region_id, iso3, base_spi, base_risk, base_phase in regions:
        # Commodity price index levels per region (stable, near-constant)
        base_price = 100.0 + (base_risk * 50.0)
        # Weekly SPI evolution — slow drift so HMM/VARLiNGAM see structure
        for week in range(0, 104):
            week_date = now - datetime.timedelta(weeks=(103 - week))
            date_str = week_date.strftime("%Y-%m-%d")

            # SPI eases slowly from drought → baseline over 2 years
            progress = week / 103.0
            spi = base_spi * (1.0 - 0.7 * progress) + 0.6 * (0.5 - progress)
            spi = round(spi, 4)

            # RainfallSignal
            rs_id = f"rs_hist_{region_id}_{week}"
            await neo4j_session.run(
                """MERGE (rs:RainfallSignal {id: $id})
                   SET rs.spi_30d = $spi,
                       rs.spi_30d_smoothed = $spi_s,
                       rs.anomaly_pct = $anom,
                       rs.dekad = 'W1',
                       rs.date = $date,
                       rs.region_id = $rid
                   WITH rs
                   MATCH (reg:Region {id: $rid})
                   MERGE (rs)-[:MEASURED_IN]->(reg)""",
                id=rs_id,
                spi=spi,
                spi_s=round(spi * 0.97, 4),
                anom=round(spi / 3.0, 4),
                date=date_str,
                rid=region_id,
            )

            # FoodPriceSignal (pct_change computed vs previous week)
            price = base_price + (1.0 - progress) * 8.0
            prev_price = base_price + (1.0 - (max(progress - 1/103, 0))) * 8.0
            pct_change = ((price - prev_price) / prev_price) * 100.0 if prev_price else 0.0
            fps_id = f"fp_hist_{region_id}_{week}"
            await neo4j_session.run(
                """MERGE (fps:FoodPriceSignal {id: $id})
                   SET fps.commodity = 'maize',
                       fps.market = $rid,
                       fps.price_usd = $price,
                       fps.pct_change_30d = $pct,
                       fps.date = $date,
                       fps.region_id = $rid
                   WITH fps
                   MATCH (reg:Region {id: $rid})
                   MERGE (fps)-[:MEASURED_IN]->(reg)""",
                id=fps_id,
                price=round(price, 2),
                pct=round(pct_change, 4),
                date=date_str,
                rid=region_id,
            )

            # IPCPhaseSignal
            ipc_id = f"ipc_hist_{region_id}_{week}"
            ipc_phase = max(1, min(5, round(base_phase + spi * 0.8)))
            await neo4j_session.run(
                """MERGE (ipc:IPCPhaseSignal {id: $id})
                   SET ipc.phase = $phase,
                       ipc.population_affected = $pop,
                       ipc.reference_date = $date,
                       ipc.region_id = $rid
                   WITH ipc
                   MATCH (reg:Region {id: $rid})
                   MERGE (ipc)-[:MEASURED_IN]->(reg)""",
                id=ipc_id,
                phase=ipc_phase,
                pop=int(200000 * (1.0 + base_risk * 3.0) * (1.0 - 0.3 * progress)),
                date=date_str,
                rid=region_id,
            )

            # StochasticSignal
            ss_id = f"ss_hist_{region_id}_{week}"
            p_drought = max(0.001, min(0.95, (-spi + 1.0) / 3.0))
            p_flood = max(0.001, min(0.95, (spi + 1.0) / 3.0))
            await neo4j_session.run(
                """MERGE (ss:StochasticSignal {id: $id})
                   SET ss.p_drought_4w = $pd,
                       ss.p_flood_4w = $pf,
                       ss.region_id = $rid,
                       ss.date = $date
                   WITH ss
                   MATCH (reg:Region {id: $rid})
                   MERGE (ss)-[:MEASURED_IN]->(reg)""",
                id=ss_id,
                pd=round(p_drought, 4),
                pf=round(p_flood, 4),
                date=date_str,
                rid=region_id,
            )

            total += 4

    print(f"  Backfilled {total} historical signal nodes (104 weeks x 11 regions x 4 types)")


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

        # 2. Update region risk score + regime.
        # Match HazardRegime by its canonical `id` (e.g. regime_drought_onset)
        # rather than `name` (e.g. "DroughtOnset") — the name-based MATCH
        # silently failed before, leaving regions unlinked from their regime.
        await neo4j_session.run(
            """MATCH (reg:Region {id: $rid})
               SET reg.current_risk_score = $score,
                   reg.current_regime = $regime
               WITH reg
               MATCH (hr:HazardRegime {id: $hid})
               MERGE (reg)-[:IN_REGIME]->(hr)""",
            rid=rid,
            score=sig['risk'],
            regime=sig['regime'],
            hid=_regime_id(sig['regime'])
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


async def seed_analytics_backfill(postgres_session):
    """Backfill a realistic dispatched-alert history for the analytics page.

    Idempotent: skips if dispatched alerts already exist. Creates sent
    alerts with dispatched_at spread over the last 30 days plus matching
    Y/N responses so the community-response charts show real numbers.
    """
    from models.postgres.alerts import Alert
    from sqlalchemy import select, text

    # Skip if we already have dispatched alerts
    existing = await postgres_session.execute(
        text("SELECT 1 FROM alerts WHERE status = 'sent' LIMIT 1")
    )
    if existing.scalar():
        print("  Dispatched alert history already exists, skipping backfill.")
        return

    now = datetime.datetime.now(datetime.timezone.utc)
    regions = [
        ('region_somalia', 'somali', 89.4, 0.85),
        ('region_south_sudan', 'english', 91.7, 0.78),
        ('region_ethiopia', 'amharic', 82.1, 0.72),
        ('region_kenya', 'swahili', 67.3, 0.55),
        ('region_sudan', 'arabic', 71.2, 0.60),
        ('region_uganda', 'english', 32.1, 0.20),
        ('region_tanzania', 'swahili', 44.8, 0.30),
        ('region_djibouti', 'french', 58.9, 0.40),
        ('region_eritrea', 'english', 62.4, 0.45),
    ]

    created = 0
    for i, (region_id, lang, risk, kelly) in enumerate(regions):
        # Spread dispatched_at over the last 30 days
        dispatched_at = now - datetime.timedelta(days=(i * 3) % 30)
        alert = Alert(
            region_id=region_id,
            language=lang,
            message_text=f"Demo dispatched advisory for {region_id}.",
            risk_score_at_trigger=risk,
            kelly_priority=kelly,
            status='sent',
            generated_at=dispatched_at - datetime.timedelta(hours=2),
            approved_at=dispatched_at - datetime.timedelta(hours=1),
            dispatched_at=dispatched_at,
            sent_count=100 + i * 20,
            delivered_count=90 + i * 15,
        )
        postgres_session.add(alert)
        await postgres_session.flush()  # get alert.id

        # Insert Y/N responses
        n_responses = 8 + (i % 5)
        for j in range(n_responses):
            resp_type = 'Y' if j % 3 != 0 else 'N'
            # Insert into alert_responses table directly
            await postgres_session.execute(
                text(
                    """INSERT INTO alert_responses (id, alert_id, response_type, responded_at, created_at)
                       VALUES (gen_random_uuid(), :aid, :rtype, :rdate, :cdate)"""
                ),
                {
                    "aid": str(alert.id),
                    "rtype": resp_type,
                    "rdate": dispatched_at + datetime.timedelta(hours=1 + j),
                    "cdate": dispatched_at + datetime.timedelta(hours=1 + j),
                },
            )
        created += 1

    await postgres_session.commit()
    print(f"  Backfilled {created} dispatched alerts with Y/N responses")


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

    # 5. Backfill 2 years of historical signal series (powers HMM/VARLiNGAM)
    print("Backfilling historical signal time series...")
    async with neo4j_client.get_session() as session:
        await seed_historical_signals(session)
    print("  Done.")

    # 6. Seed PostgreSQL data
    print("Seeding PostgreSQL alerts...")
    async with async_session_factory() as pg_session:
        await seed_postgres(pg_session)
        await seed_analytics_backfill(pg_session)
    print("  Done.")

    # 6b. Seed regime posteriors into Redis for the Regime Map
    print("Seeding regime posteriors into Redis...")
    from db.redis_client import redis_client
    await redis_client.connect()
    await register_demo_posteriors(redis_client)
    await redis_client.close()
    print("  Done.")

    # 7. Close connections
    await neo4j_client.close()

    print()
    print("✅ Demo data seeded successfully!")
    print("   Somalia, South Sudan, Ethiopia showing high risk (>80)")
    print("   Causal edges written for high-risk regions")
    print("   Historical signal series backfilled (104 weeks x 4 types x 11 regions)")
    print("   5 pending alerts ready for approval demo")
    print()
    print("   Refresh the dashboard at http://localhost:8000")
    print("   Login: admin / HazardGraph2026!")
    print()


if __name__ == '__main__':
    asyncio.run(seed())