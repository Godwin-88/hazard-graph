"""HazardGraph — Alert management API routes.

GET    /api/v1/alerts              — list alerts (paginated, filterable)
GET    /api/v1/alerts/{id}         — single alert detail
PATCH  /api/v1/alerts/{id}         — approve/reject alert
POST   /api/v1/alerts/{id}/dispatch — dispatch approved alert via SMS
GET    /api/v1/alerts/{id}/responses — Y/N responses for alert
GET    /api/v1/alerts/analytics/uptake — 30-day uptake analytics
POST   /api/v1/alerts/generate     — manual advisory generation trigger
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import DbSession, RedisDep, get_db, get_redis
from auth.jwt_service import (
    verify_token,
    get_current_user,
    require_officer,
    require_admin,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alerts", tags=["alerts"])


# ── Schemas ────────────────────────────────────────────────


class AlertOut(BaseModel):
    id: int
    region_id: str
    region_name: str = ""
    country: str = ""
    language: str
    message_text: str
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
    alert_id: int
    sent_count: int
    success_count: int
    failed_count: int
    message_ids: list[str]


class AlertResponseOut(BaseModel):
    id: int
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


@router.get("/alerts", response_model=list[AlertOut])
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
                   a.risk_score_at_trigger, a.kelly_priority, a.status,
                   a.generated_at, a.approved_at, a.dispatched_at,
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
            id=row[0],
            region_id=row[1],
            language=row[2],
            message_text=row[3],
            risk_score_at_trigger=row[4],
            kelly_priority=row[5],
            status=row[6],
            generated_at=str(row[7]) if row[7] else "",
            approved_at=str(row[8]) if row[8] else None,
            dispatched_at=str(row[9]) if row[9] else None,
            sent_count=row[10] or 0,
            delivered_count=row[11] or 0,
        ))
    return alerts


@router.get("/alerts/{alert_id}", response_model=AlertOut)
async def get_alert(
    alert_id: int,
    db: DbSession,
    user=Depends(get_current_user),
):
    """Get single alert with full detail."""
    try:
        result = await db.execute(
            text(
                """SELECT a.id, a.region_id, a.language, a.message_text,
                          a.risk_score_at_trigger, a.kelly_priority, a.status,
                          a.generated_at, a.approved_at, a.dispatched_at,
                          a.sent_count, a.delivered_count
                   FROM alerts a WHERE a.id = :aid"""
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
        id=row[0],
        region_id=row[1],
        language=row[2],
        message_text=row[3],
        risk_score_at_trigger=row[4],
        kelly_priority=row[5],
        status=row[6],
        generated_at=str(row[7]) if row[7] else "",
        approved_at=str(row[8]) if row[8] else None,
        dispatched_at=str(row[9]) if row[9] else None,
        sent_count=row[10] or 0,
        delivered_count=row[11] or 0,
    )


@router.patch("/alerts/{alert_id}")
async def patch_alert(
    alert_id: int,
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
                       WHERE id = :aid"""
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
                       WHERE id = :aid"""
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


@router.post("/alerts/{alert_id}/dispatch", response_model=DispatchResultOut)
async def dispatch_alert(
    alert_id: int,
    db: DbSession,
    user=Depends(require_officer),
):
    """Dispatch an approved alert via Africa's Talking SMS."""
    # Fetch alert
    try:
        result = await db.execute(
            text("SELECT status, message_text, region_id FROM alerts WHERE id = :aid"),
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
            alert_id=result.alert_id,
            sent_count=result.sent_count,
            success_count=result.success_count,
            failed_count=result.failed_count,
            message_ids=result.message_ids,
        )
    except Exception as exc:
        logger.error("Dispatch failed for alert %s: %s", alert_id, exc)
        raise HTTPException(status_code=500, detail=f"Dispatch failed: {exc}")


@router.get("/alerts/{alert_id}/responses", response_model=list[AlertResponseOut])
async def get_alert_responses(
    alert_id: int,
    db: DbSession,
    user=Depends(get_current_user),
):
    """Get all Y/N responses for an alert."""
    try:
        result = await db.execute(
            text(
                """SELECT id, response_type, response_text, responded_at
                   FROM alert_responses
                   WHERE alert_id = :aid
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
            id=row[0],
            response_type=row[1],
            response_text=row[2],
            responded_at=str(row[3]) if row[3] else "",
        )
        for row in rows
    ]


@router.get("/alerts/analytics/uptake", response_model=list[UptakeAnalyticsOut])
async def get_uptake_analytics(
    db: DbSession,
    redis: RedisDep,
    user=Depends(get_current_user),
):
    """Get 30-day uptake analytics per region. Redis cached 15 min."""
    # Try cache
    try:
        cached = await redis.get("analytics:uptake")
        if cached:
            import json
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
                   WHERE a.dispatched_at >= NOW() - INTERVAL '30 days'
                   GROUP BY a.region_id
                   ORDER BY a.region_id"""
            ),
        )
        rows = result.fetchall()
    except Exception as exc:
        logger.error("Failed to fetch uptake analytics: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch analytics")

    analytics = [
        UptakeAnalyticsOut(
            region_id=row[0],
            sent_count=row[1] or 0,
            response_rate=round(row[2] or 0.0, 4),
            y_rate=round(row[3] or 0.0, 4),
            n_rate=round(row[4] or 0.0, 4),
        )
        for row in rows
    ]

    # Cache 15 min
    try:
        import json
        await redis.set("analytics:uptake", json.dumps([a.dict() for a in analytics]), ex=900)
    except Exception:
        pass

    return analytics


@router.post("/alerts/generate")
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