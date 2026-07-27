"""HazardGraph — Inbound SMS feedback handler.

Handles 2-way SMS responses from Africa's Talking inbound webhook.
Farmers reply Y or N to confirm action taken.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import text

logger = logging.getLogger(__name__)

RESPONSE_YES = "Samahani, hatujui nambari yako?"
RESPONSE_NO = "Asante! Tutaendelea kukusaidia."
RESPONSE_INVALID = "Jibu Y au N tu. Asante."


async def handle_inbound(
    from_phone: str,
    message: str,
    received_at: datetime,
    postgres_session,
) -> str:
    """Process an inbound SMS response from a farmer.

    Args:
        from_phone: Sender's phone number (E.164)
        message: Raw SMS text
        received_at: When the message was received
        postgres_session: Async SQLAlchemy session

    Returns:
        Reply SMS text in appropriate language
    """
    normalised = message.strip().upper()
    first_char = normalised[:1] if normalised else ""

    # Find most recent sent alert for this phone
    try:
        result = await postgres_session.execute(
            text(
                """SELECT a.id, a.region_id, a.language
                   FROM alerts a
                   JOIN alert_deliveries d ON d.alert_id = a.id
                   WHERE d.recipient = :phone
                     AND a.status = 'sent'
                   ORDER BY a.dispatched_at DESC
                   LIMIT 1"""
            ),
            {"phone": from_phone},
        )
        row = result.fetchone()
    except Exception as exc:
        logger.error("Failed to query recent alert for %s: %s", from_phone, exc)
        return "Samahani, hitilafu ya mfumo. Tafadhali jaribu tena baadaye."

    if not row:
        logger.info("No recent alert found for %s", from_phone)
        return "Samahani, hatujui nambari yako."

    alert_id = row[0]
    region_id = row[1]
    language = row[2] or "en"

    # Determine response type
    if first_char == "Y":
        response_type = "Y"
        reply_text = "Asante! Tutaendelea kukusaidia."
    elif first_char == "N":
        response_type = "N"
        reply_text = "Asante. Tafadhali wasiliana na afisa wa kilimo kwa mwongozo zaidi."
    else:
        response_type = "invalid"
        reply_text = "Jibu Y au N tu. Asante."

    # Persist response
    try:
        # Check if alert_responses table exists, if not use generic response
        await postgres_session.execute(
            text(
                """INSERT INTO alert_responses
                   (alert_id, user_id, response_type, response_text, responded_at, created_at)
                   VALUES (:aid, NULL, :rtype, :rtext, :now, :now)"""
            ),
            {
                "aid": alert_id,
                "rtype": response_type,
                "rtext": message.strip(),
                "now": received_at,
            },
        )
        await postgres_session.commit()
        logger.info(
            "Recorded response %s from %s for alert %s",
            response_type,
            from_phone,
            alert_id,
        )
    except Exception as exc:
        logger.error("Failed to persist response: %s", exc)
        await postgres_session.rollback()

    # Log to audit
    try:
        from db.postgres_client import async_session_factory as _asf
        from models.postgres.audit import AuditLog
        async with _asf() as audit_session:
            log = AuditLog(
                action="inbound_sms_response",
                entity_type="alert",
                entity_id=str(alert_id),
                details=f"Phone: {from_phone}, Response: {response_type}",
            )
            audit_session.add(log)
            await audit_session.commit()
    except Exception as exc:
        logger.warning("Failed to log audit: %s", exc)

    return reply_text