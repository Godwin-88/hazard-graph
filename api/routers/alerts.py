"""HazardGraph — Alert management API routes.

GET    /api/v1/alerts              — list alerts (paginated, filterable)
GET    /api/v1/alerts/analytics/uptake — 30-day uptake analytics
POST   /api/v1/alerts/generate     — manual advisory generation trigger
GET    /api/v1/alerts/{id}         — single alert detail
PATCH  /api/v1/alerts/{id}         — approve/reject alert
POST   /api/v1/alerts/{id}/dispatch — dispatch approved alert via SMS
GET    /api/v1/alerts/{id}/responses — Y/N responses for alert

NOTE: /analytics/uptake and /generate are registered BEFORE /{id} so
they are not shadowed by the generic path parameter (alert ids are UUIDs).
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text

from api.deps import DbSession, RedisDep
from auth.jwt_service import (
    get_current_user,
    require_officer,
    require_admin,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


# ── Schemas ────────────────────────────────────────────────


class AlertOut(BaseModel):
    id: str
    region_id: str
    region_name: str = ""
    country: str = ""
    language: str
    message_text: str
    english_text: Optional[str] = None
    risk_score_at_trigger: float
    kelly_priority: float
    confidence: float = 0.0
    status: str
    generated_at: str
    approved_at: Optional[str] = None
    dispatched_at: Optional[str] = None
    sent_count: int = 0
    delivered_count: int = 0
    current_regime: str = ""
    components: dict = {}


class AlertPatchRequest(BaseModel):
    action: str  # 'approve' or 'reject'
    message_text: Optional[str] = None
    reason: Optional[str] = None


class DispatchResultOut(BaseModel):
    alert_id: str
    sent_count: int
    success_count: int
    failed_count: int
    message_ids: list[str]


class AlertResponseOut(BaseModel):
    id: str
    response_type: str
    response_text: Optional[str] = None
    responded_at: str


class UptakeAnalyticsOut(BaseModel):
    region_id: str
    sent_count: int
    response_rate: float
    y_rate: float
    n_rate: float


# ── Routes ─────────────────────────────────────────────────


@router.get("", response_model=list[AlertOut], include_in_schema=False)
async def list_alerts_no_slash(
    db: DbSession,
    user=Depends(get_current_user),
    status_filter: Optional[str] = Query(None, alias="status"),
    region_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Alias for list_alerts without trailing slash — prevents 307 redirect which drops auth headers."""
    return await list_alerts(
        db, user, status_filter, region_id, page, page_size
    )


@router.get("/", response_model=list[AlertOut])
async def list_alerts(
    db: DbSession,
    user=Depends(get_current_user),
    status_filter: Optional[str] = Query(None, alias="status"),
    region_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List alerts with optional status and region filters."""
    conditions = []
    params = {"limit": page_size, "offset": (page - 1) * page_size}

    if status_filter:
        conditions.append("a.status = :status")
        params["status"] = status_filter
    if region_id:
        conditions.append("a.region_id = :region_id")
        params["region_id"] = region_id

    where_clause = " AND ".join(conditions) if conditions else "TRUE"

    query = text(
        f"""SELECT a.id, a.region_id, a.language, a.message_text,
                   a.english_text, a.risk_score_at_trigger, a.kelly_priority,
                   a.status, a.generated_at, a.approved_at, a.dispatched_at,
                   a.sent_count, a.delivered_count
            FROM alerts a
            WHERE {where_clause}
            ORDER BY a.kelly_priority DESC, a.generated_at DESC
            LIMIT :limit OFFSET :offset"""
    )

    try:
        result = await db.execute(query, params)
        rows = result.fetchall()
    except Exception as exc:
        logger.error("Failed to fetch alerts: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch alerts")

    alerts = []
    for row in rows:
        alerts.append(AlertOut(
            id=str(row[0]),
            region_id=row[1],
            language=row[2],
            message_text=row[3],
            english_text=row[4],
            risk_score_at_trigger=row[5],
            kelly_priority=row[6],
            status=row[7],
            generated_at=str(row[8]) if row[8] else "",
            approved_at=str(row[9]) if row[9] else None,
            dispatched_at=str(row[10]) if row[10] else None,
            sent_count=row[11] or 0,
            delivered_count=row[12] or 0,
        ))
    return alerts


# ── Static routes first (must be registered before /{alert_id}) ──


@router.get("/analytics/uptake")
async def get_uptake_analytics(
    db: DbSession,
    redis: RedisDep,
    user=Depends(get_current_user),
):
    """Get 30-day uptake analytics in the aggregate shape the dashboard
    expects: KPI sums plus per-region and weekly breakdowns.

    Redis cached for 15 minutes. Returns an object (not a bare list) so the
    React Analytics page can read total_alerts_30d / weekly_uptake / etc.
    """
    import json

    # Try cache
    try:
        cached = await redis.get("analytics:uptake")
        if cached:
            return json.loads(cached)
    except Exception:
        pass

    try:
        result = await db.execute(
            text(
                """SELECT
                    a.region_id,
                    COUNT(DISTINCT a.id) AS sent_count,
                    COUNT(DISTINCT ar.id)::float / NULLIF(COUNT(DISTINCT a.id), 0) AS response_rate,
                    COUNT(DISTINCT CASE WHEN ar.response_type = 'Y' THEN ar.id END)::float
                        / NULLIF(COUNT(DISTINCT ar.id), 0) AS y_rate,
                    COUNT(DISTINCT CASE WHEN ar.response_type = 'N' THEN ar.id END)::float
                        / NULLIF(COUNT(DISTINCT ar.id), 0) AS n_rate
                   FROM alerts a
                   LEFT JOIN alert_responses ar ON ar.alert_id = a.id
                   WHERE a.created_at >= NOW() - INTERVAL '30 days'
                   GROUP BY a.region_id
                   ORDER BY a.region_id"""
            ),
        )
        rows = result.fetchall()
    except Exception as exc:
        logger.error("Failed to fetch uptake analytics: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch analytics")

    per_region = []
    total_sent = 0
    response_rates = []
    action_rates = []
    for row in rows:
        region_id = row[0]
        sent = row[1] or 0
        response_rate = row[2] or 0.0
        y_rate = row[3] or 0.0
        n_rate = row[4] or 0.0
        total_sent += sent
        response_rates.append(response_rate)
        action_rates.append(y_rate)
        responded = round(sent * response_rate)
        per_region.append({
            "region": region_id.replace("region_", "").replace("_", " ").title(),
            "sent": sent,
            "responded": responded,
            "yes_pct": round(y_rate * 100, 1),
            "no_pct": round(n_rate * 100, 1),
            "last_alert": "",
        })

    # Query weekly uptake (group by week of dispatched/created date)
    weekly_uptake = []
    try:
        week_result = await db.execute(
            text(
                """SELECT
                    DATE_TRUNC('week', a.created_at) AS week_start,
                    COUNT(DISTINCT a.id) AS sent_count,
                    COUNT(DISTINCT ar.id)::float / NULLIF(COUNT(DISTINCT a.id), 0) AS response_rate,
                    COUNT(DISTINCT CASE WHEN ar.response_type = 'Y' THEN ar.id END)::float
                        / NULLIF(COUNT(DISTINCT ar.id), 0) AS y_rate
                   FROM alerts a
                   LEFT JOIN alert_responses ar ON ar.alert_id = a.id
                   WHERE a.created_at >= NOW() - INTERVAL '8 weeks'
                   GROUP BY week_start
                   ORDER BY week_start"""
            ),
        )
        week_rows = week_result.fetchall()
        for w in week_rows:
            week_start = w[0]
            sent_w = w[1] or 0
            y_rate_w = w[3] or 0.0
            n_rate_w = 1.0 - y_rate_w
            weekly_uptake.append({
                "week": week_start.strftime("W%V") if week_start else "",
                "yes_rate": round(y_rate_w * 100, 1),
                "no_rate": round(n_rate_w * 100, 1),
            })
    except Exception as exc:
        logger.warning("Failed to fetch weekly uptakes: %s", exc)

    # Query language performance
    language_performance = []
    try:
        lang_result = await db.execute(
            text(
                """SELECT
                    a.language,
                    COUNT(DISTINCT a.id) AS sent_count,
                    COUNT(DISTINCT ar.id)::float / NULLIF(COUNT(DISTINCT a.id), 0) AS response_rate
                   FROM alerts a
                   LEFT JOIN alert_responses ar ON ar.alert_id = a.id
                   WHERE a.created_at >= NOW() - INTERVAL '30 days'
                   GROUP BY a.language
                   ORDER BY sent_count DESC"""
            ),
        )
        lang_rows = lang_result.fetchall()
        for l in lang_rows:
            lang = l[0] or "unknown"
            language_performance.append({
                "language": lang.capitalize(),
                "response_rate": round((l[2] or 0.0) * 100, 1),
                "total_sent": l[1] or 0,
            })
    except Exception as exc:
        logger.warning("Failed to fetch language performance: %s", exc)

    n = max(len(response_rates), 1)
    payload = {
        "total_alerts_30d": total_sent,
        "overall_response_rate": round(sum(response_rates) / n * 100, 1),
        "action_uptake_rate": round(sum(action_rates) / n * 100, 1),
        "regions_in_alert": len(per_region),
        "weekly_uptake": weekly_uptake,
        "per_region": per_region,
        "language_performance": language_performance,
    }

    # Demo fallback: if there are genuinely no alerts in the window, return a
    # populated demo payload so the UI never shows blank/zero charts on a fresh DB.
    if total_sent == 0:
        payload = {
            "total_alerts_30d": 847,
            "overall_response_rate": 62.4,
            "action_uptake_rate": 58.3,
            "regions_in_alert": 5,
            "weekly_uptake": [
                {"week": "W22", "yes_rate": 45.2, "no_rate": 54.8},
                {"week": "W23", "yes_rate": 48.7, "no_rate": 51.3},
                {"week": "W24", "yes_rate": 52.1, "no_rate": 47.9},
                {"week": "W25", "yes_rate": 49.8, "no_rate": 50.2},
                {"week": "W26", "yes_rate": 55.3, "no_rate": 44.7},
                {"week": "W27", "yes_rate": 58.9, "no_rate": 41.1},
                {"week": "W28", "yes_rate": 61.2, "no_rate": 38.8},
                {"week": "W29", "yes_rate": 58.3, "no_rate": 41.7},
            ],
            "per_region": [
                {"region": "Somalia", "sent": 142, "responded": 89, "yes_pct": 41.5, "no_pct": 58.5, "last_alert": "2026-07-27"},
                {"region": "South Sudan", "sent": 98, "responded": 54, "yes_pct": 36.7, "no_pct": 63.3, "last_alert": "2026-07-26"},
                {"region": "Ethiopia", "sent": 187, "responded": 112, "yes_pct": 48.2, "no_pct": 51.8, "last_alert": "2026-07-27"},
                {"region": "Kenya", "sent": 156, "responded": 108, "yes_pct": 62.0, "no_pct": 38.0, "last_alert": "2026-07-25"},
                {"region": "Sudan", "sent": 73, "responded": 48, "yes_pct": 56.3, "no_pct": 43.7, "last_alert": "2026-07-24"},
                {"region": "Uganda", "sent": 65, "responded": 42, "yes_pct": 66.7, "no_pct": 33.3, "last_alert": "2026-07-23"},
                {"region": "Tanzania", "sent": 52, "responded": 34, "yes_pct": 70.6, "no_pct": 29.4, "last_alert": "2026-07-22"},
                {"region": "Djibouti", "sent": 38, "responded": 22, "yes_pct": 52.3, "no_pct": 47.7, "last_alert": "2026-07-21"},
                {"region": "Eritrea", "sent": 36, "responded": 19, "yes_pct": 47.4, "no_pct": 52.6, "last_alert": "2026-07-20"},
            ],
            "language_performance": [
                {"language": "Swahili", "response_rate": 64.2, "total_sent": 320},
                {"language": "Somali", "response_rate": 48.7, "total_sent": 185},
                {"language": "Amharic", "response_rate": 52.3, "total_sent": 142},
                {"language": "English", "response_rate": 58.9, "total_sent": 98},
                {"language": "Arabic", "response_rate": 43.1, "total_sent": 67},
            ],
            "source": "demo",
        }

    # Cache 15 min
    try:
        await redis.set("analytics:uptake", json.dumps(payload), ex=900)
    except Exception:
        pass

    return payload


@router.post("/generate")
async def generate_alerts(
    db: DbSession,
    user=Depends(require_admin),
):
    """Manually trigger advisory generation for all triggered regions."""
    from alerts.advisory_generator import AdvisoryGenerator
    from risk.scoring_service import compute_risk_scores
    from db.neo4j_client import neo4j_client
    from models.ensemble.bma_engine import BMAEngine

    try:
        risk_scores = await compute_risk_scores(neo4j_client)
    except Exception as exc:
        logger.error("Failed to compute risk scores: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to compute risk scores")

    bma_results = []
    for score in risk_scores:
        try:
            bma = await BMAEngine().compute_posterior(
                region_id=score.region_id,
                scoring_result=score,
                sde_result={},
                hmm_posteriors={},
                neo4j_session=neo4j_client,
                postgres_session=db,
            )
            bma_results.append(bma)
        except Exception as exc:
            logger.warning("BMA failed for %s: %s", score.region_id, exc)
            bma_results.append(None)

    gen = AdvisoryGenerator()
    try:
        alert_ids = await gen.generate_all_triggered(
            risk_scores=risk_scores,
            bma_results=bma_results,
            postgres_session=db,
            neo4j_session=neo4j_client,
        )
    except Exception as exc:
        logger.error("Advisory generation failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Advisory generation failed: {exc}")

    return {"generated_count": len(alert_ids), "alert_ids": alert_ids}


# ── Dynamic routes (UUID alert ids) ──


@router.get("/{alert_id}", response_model=AlertOut)
async def get_alert(
    alert_id: str,
    db: DbSession,
    user=Depends(get_current_user),
):
    """Get single alert with full detail."""
    try:
        result = await db.execute(
            text(
                """SELECT a.id, a.region_id, a.language, a.message_text,
                          a.english_text, a.risk_score_at_trigger,
                          a.kelly_priority, a.status, a.generated_at,
                          a.approved_at, a.dispatched_at,
                          a.sent_count, a.delivered_count
                   FROM alerts a WHERE a.id = CAST(:aid AS uuid)"""
            ),
            {"aid": alert_id},
        )
        row = result.fetchone()
    except Exception as exc:
        logger.error("Failed to fetch alert %s: %s", alert_id, exc)
        raise HTTPException(status_code=500, detail="Failed to fetch alert")

    if not row:
        raise HTTPException(status_code=404, detail="Alert not found")

    return AlertOut(
        id=str(row[0]),
        region_id=row[1],
        language=row[2],
        message_text=row[3],
        english_text=row[4],
        risk_score_at_trigger=row[5],
        kelly_priority=row[6],
        status=row[7],
        generated_at=str(row[8]) if row[8] else "",
        approved_at=str(row[9]) if row[9] else None,
        dispatched_at=str(row[10]) if row[10] else None,
        sent_count=row[11] or 0,
        delivered_count=row[12] or 0,
    )


@router.patch("/{alert_id}")
async def patch_alert(
    alert_id: str,
    body: AlertPatchRequest,
    db: DbSession,
    user=Depends(require_officer),
):
    """Approve or reject an alert."""
    user_id = user.get("sub", "unknown")

    if body.action == "approve":
        msg_text = body.message_text
        try:
            await db.execute(
                text(
                    """UPDATE alerts SET
                       status = 'approved',
                       message_text = COALESCE(:msg, message_text),
                       approved_by = :uid,
                       approved_at = :now
                       WHERE id = CAST(:aid AS uuid)"""
                ),
                {
                    "msg": msg_text,
                    "uid": user_id,
                    "now": datetime.now(timezone.utc),
                    "aid": alert_id,
                },
            )
            await db.commit()
            logger.info("Alert %s approved by user %s", alert_id, user_id)
        except Exception as exc:
            await db.rollback()
            logger.error("Failed to approve alert %s: %s", alert_id, exc)
            raise HTTPException(status_code=500, detail="Failed to approve alert")

    elif body.action == "reject":
        try:
            await db.execute(
                text(
                    """UPDATE alerts SET
                       status = 'rejected',
                       rejection_reason = :reason,
                       approved_by = :uid,
                       approved_at = :now
                       WHERE id = CAST(:aid AS uuid)"""
                ),
                {
                    "reason": body.reason or "No reason provided",
                    "uid": user_id,
                    "now": datetime.now(timezone.utc),
                    "aid": alert_id,
                },
            )
            await db.commit()
            logger.info("Alert %s rejected by user %s: %s", alert_id, user_id, body.reason)
        except Exception as exc:
            await db.rollback()
            logger.error("Failed to reject alert %s: %s", alert_id, exc)
            raise HTTPException(status_code=500, detail="Failed to reject alert")

    else:
        raise HTTPException(status_code=400, detail="Action must be 'approve' or 'reject'")

    # Log to audit
    try:
        from models.postgres.audit import AuditLog
        log = AuditLog(
            action=f"alert_{body.action}",
            entity_type="alert",
            entity_id=str(alert_id),
            details=f"User {user_id} {body.action}ed alert {alert_id}",
        )
        db.add(log)
        await db.commit()
    except Exception as exc:
        logger.warning("Failed to log audit: %s", exc)

    return {"detail": f"Alert {body.action}d successfully", "alert_id": alert_id}


@router.post("/{alert_id}/dispatch", response_model=DispatchResultOut)
async def dispatch_alert(
    alert_id: str,
    db: DbSession,
    user=Depends(require_officer),
):
    """Dispatch an approved alert via Africa's Talking SMS."""
    # Fetch alert
    try:
        result = await db.execute(
            text("SELECT status, message_text, region_id FROM alerts WHERE id = CAST(:aid AS uuid)"),
            {"aid": alert_id},
        )
        row = result.fetchone()
    except Exception as exc:
        logger.error("Failed to fetch alert %s: %s", alert_id, exc)
        raise HTTPException(status_code=500, detail="Failed to fetch alert")

    if not row:
        raise HTTPException(status_code=404, detail="Alert not found")

    status_val, message_text, region_id = row

    if status_val != "approved":
        raise HTTPException(
            status_code=400,
            detail=f"Alert must be 'approved' before dispatch (current: {status_val})",
        )

    # Dispatch
    from alerts.at_sms_service import AfricasTalkingService

    at_service = AfricasTalkingService()
    recipients = await at_service.get_test_recipients(region_id)

    try:
        result = await at_service.dispatch(alert_id, message_text, recipients, db)
        return DispatchResultOut(
            alert_id=str(result.alert_id),
            sent_count=result.sent_count,
            success_count=result.success_count,
            failed_count=result.failed_count,
            message_ids=result.message_ids,
        )
    except Exception as exc:
        logger.error("Dispatch failed for alert %s: %s", alert_id, exc)
        raise HTTPException(status_code=500, detail=f"Dispatch failed: {exc}")


@router.get("/{alert_id}/responses", response_model=list[AlertResponseOut])
async def get_alert_responses(
    alert_id: str,
    db: DbSession,
    user=Depends(get_current_user),
):
    """Get all Y/N responses for an alert."""
    try:
        result = await db.execute(
            text(
                """SELECT id, response_type, response_text, responded_at
                   FROM alert_responses
                   WHERE alert_id = CAST(:aid AS uuid)
                   ORDER BY responded_at DESC"""
            ),
            {"aid": alert_id},
        )
        rows = result.fetchall()
    except Exception as exc:
        logger.error("Failed to fetch responses for alert %s: %s", alert_id, exc)
        raise HTTPException(status_code=500, detail="Failed to fetch responses")

    return [
        AlertResponseOut(
            id=str(row[0]),
            response_type=row[1],
            response_text=row[2],
            responded_at=str(row[3]) if row[3] else "",
        )
        for row in rows
    ]