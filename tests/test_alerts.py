"""Test alert generation and dispatch."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestAdvisoryGeneration:
    @pytest.mark.asyncio
    async def test_advisory_max_160_chars(self, sample_risk_score):
        """Advisory must never exceed 160 characters."""
        from alerts.advisory_generator import AdvisoryGenerator
        gen = AdvisoryGenerator()
        mock_response = MagicMock()
        mock_response.choices[0].message.content = (
            'Hali ya hewa inaonyesha upungufu wa mvua. '
            'Vuna malisho na hifadhi maji wiki hii.'
        )
        with patch('groq.AsyncGroq') as mock_groq:
            mock_groq.return_value.chat.completions.create = \
                AsyncMock(return_value=mock_response)
            advisory = await gen.generate(
                region_id=sample_risk_score.region_id,
                region_name=sample_risk_score.name,
                country=sample_risk_score.country,
                score=sample_risk_score.score,
                confidence=0.85,
                components=sample_risk_score.components,
                current_regime=sample_risk_score.current_regime,
                sde_interpretation="drought likely",
                spi_interpretation="below normal",
                food_interpretation="rising",
                ipc_interpretation="stressed",
                top_features=["rainfall", "food"],
                language="swahili",
                lang_code="sw",
                season_context="Long rains season",
            )
        assert len(advisory) <= 160, (
            f"Advisory too long: {len(advisory)} chars — '{advisory}'"
        )
        assert len(advisory) > 0

    @pytest.mark.asyncio
    async def test_advisory_fallback_when_groq_fails(self, sample_risk_score):
        """Fallback advisory should be non-empty and under 160 chars."""
        from alerts.advisory_generator import AdvisoryGenerator
        gen = AdvisoryGenerator()
        with patch('groq.AsyncGroq', side_effect=Exception("No API")):
            advisory = await gen.generate(
                region_id=sample_risk_score.region_id,
                region_name=sample_risk_score.name,
                country=sample_risk_score.country,
                score=sample_risk_score.score,
                confidence=0.85,
                components=sample_risk_score.components,
                current_regime=sample_risk_score.current_regime,
                sde_interpretation="drought likely",
                spi_interpretation="below normal",
                food_interpretation="rising",
                ipc_interpretation="stressed",
            )
        assert len(advisory) > 0
        assert len(advisory) <= 160

    @pytest.mark.asyncio
    async def test_inbound_y_response_stored(
        self, postgres_session, neo4j_driver
    ):
        """Y response from farmer is stored in alert_responses."""
        from alerts.feedback_handler import handle_inbound
        from datetime import datetime
        from models.postgres.alerts import Alert, AlertDelivery
        from sqlalchemy import insert, select, text
        # Seed: alert + delivery for test phone
        await postgres_session.execute(
            text(
                "INSERT INTO alerts (id, region_id, language, message_text, "
                "risk_score_at_trigger, status, generated_at, created_at, updated_at) "
                "VALUES (:id, :rid, :lang, :msg, :score, :status, :now, :now, :now) "
                "ON CONFLICT (id) DO NOTHING"
            ),
            {
                "id": "00000000-0000-0000-0000-000000009999",
                "rid": "kenya",
                "lang": "swahili",
                "msg": "Test advisory",
                "score": 67.0,
                "status": "sent",
                "now": datetime.utcnow(),
            }
        )
        await postgres_session.execute(
            text(
                "INSERT INTO alert_deliveries (alert_id, recipient_phone, "
                "at_message_id, status, dispatched_at) "
                "VALUES (:alert_id, :phone, :msg_id, :status, :now) "
                "ON CONFLICT DO NOTHING"
            ),
            {
                "alert_id": "00000000-0000-0000-0000-000000009999",
                "phone": "+254700000099",
                "msg_id": "test-msg-id",
                "status": "Success",
                "now": datetime.utcnow(),
            }
        )
        await postgres_session.commit()

        reply = await handle_inbound(
            from_phone='+254700000099',
            message='Y',
            received_at=datetime.utcnow(),
            postgres_session=postgres_session
        )
        assert 'Asante' in reply
        # Verify stored
        from models.postgres.alerts import AlertResponse
        result = await postgres_session.execute(
            select(AlertResponse).where(
                AlertResponse.alert_id == "00000000-0000-0000-0000-000000009999",
                AlertResponse.response == 'Y'
            )
        )
        assert result.scalar_one_or_none() is not None