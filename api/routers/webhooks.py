"""HazardGraph — Africa's Talking webhook handlers.

POST /api/v1/webhooks/at-delivery — Delivery report webhook (AT → us)
POST /api/v1/webhooks/at-inbound  — Inbound SMS webhook (farmer → us)

NO auth on these routes — AT posts here directly.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/at-delivery")
async def at_delivery_report(
    request: Request,
    id: str = Form(""),
    status: str = Form(""),
    phoneNumber: str = Form(""),
    networkCode: str = Form(""),
    failureReason: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    """Handle Africa's Talking delivery report callback.

    AT sends form-encoded POST with id, status, phoneNumber, etc.
    """
    logger.info(
        "Delivery report: id=%s status=%s phone=%s fail=%s",
        id, status, phoneNumber, failureReason,
    )

    if not id:
        logger.warning("Delivery report without message ID — ignoring")
        return "OK"

    try:
        await db.execute(
            text(
                """UPDATE alert_deliveries
                   SET status = :status, delivered_at = :now
                   WHERE at_message_id = :msg_id
                   OR (recipient = :phone AND status = 'sent')"""
            ),
            {
                "status": status.lower() if status else "unknown",
                "now": datetime.now(timezone.utc),
                "msg_id": id,
                "phone": phoneNumber,
            },
        )
        await db.commit()
        logger.info("Updated delivery status for msg %s: %s", id, status)
    except Exception as exc:
        logger.error("Failed to update delivery status: %s", exc)
        await db.rollback()

    # AT requires 200 "OK" response
    return "OK"


@router.post("/at-inbound")
async def at_inbound_sms(
    request: Request,
    from_: str = Form("", alias="from"),
    to: str = Form(""),
    text: str = Form(""),
    date: str = Form(""),
    id: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    """Handle Africa's Talking inbound SMS callback.

    AT sends form-encoded POST with from, to, text, date, id.
    Response body is the reply SMS text AT delivers back to sender.
    """
    logger.info(
        "Inbound SMS: from=%s to=%s text=%s date=%s id=%s",
        from_, to, text, date, id,
    )

    if not from_ or not text:
        logger.warning("Inbound SMS missing from or text — ignoring")
        return "Samahani, ujumbe wako haujaeleweka. Tafadhali jaribu tena."

    try:
        received_at = datetime.now(timezone.utc)
        reply = await handle_inbound(
            from_phone=from_,
            message=text,
            received_at=received_at,
            postgres_session=db,
        )
    except Exception as exc:
        logger.error("Failed to handle inbound SMS: %s", exc)
        reply = "Samahani, hitilafu ya mfumo. Tafadhali jaribu tena baadaye."

    return reply


async def handle_inbound(
    from_phone: str,
    message: str,
    received_at: datetime,
    postgres_session,
) -> str:
    """Process inbound SMS — delegate to feedback handler."""
    from alerts.feedback_handler import handle_inbound as fb_handle
    return await fb_handle(from_phone, message, received_at, postgres_session)