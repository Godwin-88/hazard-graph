"""HazardGraph — Africa's Talking SMS dispatch service.

Integrates with Africa's Talking sandbox for free SMS testing.
All SMS operations wrapped in run_in_executor since AT SDK is synchronous.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import text

from config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class DispatchResult:
    alert_id: str
    sent_count: int
    success_count: int
    failed_count: int
    message_ids: list[str]


class AfricasTalkingService:
    """Africa's Talking SMS dispatch service."""

    def __init__(self):
        self.username = settings.AT_USERNAME
        self.api_key = settings.AT_API_KEY
        self.env = settings.AT_ENV
        self.sender = settings.AT_SENDER
        self._initialized = False
        self._sms = None

    def _ensure_initialized(self):
        """Lazy initialise AT SDK."""
        if not self._initialized:
            import africastalking
            africastalking.initialize(
                username=self.username,
                api_key=self.api_key,
            )
            self._sms = africastalking.SMS
            self._initialized = True

    async def dispatch(
        self,
        alert_id: str,
        message: str,
        recipients: list[str],
        postgres_session,
    ) -> DispatchResult:
        """Dispatch SMS via Africa's Talking.

        Args:
            alert_id: PostgreSQL alert ID
            message: SMS text (max 160 chars)
            recipients: List of E.164 phone numbers
            postgres_session: Async SQLAlchemy session

        Returns:
            DispatchResult with delivery stats
        """
        if not recipients:
            logger.warning("No recipients for alert %s", alert_id)
            return DispatchResult(
                alert_id=alert_id,
                sent_count=0,
                success_count=0,
                failed_count=0,
                message_ids=[],
            )

        self._ensure_initialized()

        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._sms.send(
                    message=message,
                    recipients=recipients,
                    sender_id=self.sender,
                ),
            )
        except Exception as exc:
            logger.error("AT SMS dispatch failed for alert %s: %s", alert_id, exc)
            # Update alert status
            try:
                await postgres_session.execute(
                    text("UPDATE alerts SET status = 'dispatch_failed' WHERE id = CAST(:aid AS uuid)"),
                    {"aid": alert_id},
                )
                await postgres_session.commit()
            except Exception as db_exc:
                logger.error("Failed to update alert status: %s", db_exc)
            raise

        # Parse AT response
        recipients_data = response.get("SMSMessageData", {}).get("Recipients", [])
        message_ids: list[str] = []
        success_count = 0
        failed_count = 0

        for recipient in recipients_data:
            status = recipient.get("status", "Failed")
            cost = recipient.get("cost", "0")
            msg_id = recipient.get("messageId", "")
            phone = recipient.get("number", "")

            message_ids.append(msg_id)

            if status == "Success":
                success_count += 1
            else:
                failed_count += 1

            # Write delivery record
            try:
                await postgres_session.execute(
                    text(
                        """INSERT INTO alert_deliveries
                           (alert_id, channel, recipient, status, delivered_at, created_at)
                           VALUES (CAST(:aid AS uuid), 'sms', :phone, :status, :now, :now)"""
                    ),
                    {
                        "aid": alert_id,
                        "phone": phone,
                        "status": status.lower(),
                        "now": datetime.now(timezone.utc),
                    },
                )
            except Exception as exc:
                logger.warning("Failed to write delivery record: %s", exc)

        # Update alert
        try:
            await postgres_session.execute(
                text(
                    """UPDATE alerts SET
                       status = 'sent',
                       sent_count = :sent,
                       delivered_count = :delivered,
                       dispatched_at = :now
                       WHERE id = CAST(:aid AS uuid)"""
                ),
                {
                    "sent": len(recipients),
                    "delivered": success_count,
                    "now": datetime.now(timezone.utc),
                    "aid": alert_id,
                },
            )
            await postgres_session.commit()
        except Exception as exc:
            logger.error("Failed to update alert %s: %s", alert_id, exc)
            await postgres_session.rollback()

        logger.info(
            "Dispatched alert %s: %d sent, %d success, %d failed",
            alert_id,
            len(recipients),
            success_count,
            failed_count,
        )

        return DispatchResult(
            alert_id=alert_id,
            sent_count=len(recipients),
            success_count=success_count,
            failed_count=failed_count,
            message_ids=message_ids,
        )

    async def get_test_recipients(self, region_id: str) -> list[str]:
        """Get test recipients for a region.

        For demo/sandbox: return hardcoded test numbers.
        In production: query PostgreSQL recipients table.
        """
        # Sandbox test numbers — AT accepts any E.164 format
        return [
            "+254700000001",
            "+254700000002",
            "+254700000003",
        ]