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
            from models.ensemble.bma_engine import BMAResult
            bma = BMAResult(
                region_id='kenya', posterior_risk=0.72,
                epistemic_uncertainty=0.10, confidence='High',
                model_weights={}, component_probabilities={}
            )
            advisory = await gen.generate(sample_risk_score, bma)
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
            from models.ensemble.bma_engine import BMAResult
            bma = BMAResult(
                region_id='kenya', posterior_risk=0.72,
                epistemic_uncertainty=0.10, confidence='High',
                model_weights={}, component_probabilities={}
            )
            advisory = await gen.generate(sample_risk_score, bma)
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
        from sqlalchemy import insert, select
        # Seed: alert + delivery for test phone
        await postgres_session.execute(insert(Alert).values(
            id=9999, region_id='kenya', language='swahili',
            message_text='Test advisory', risk_score_at_trigger=67.0,
            status='sent', kelly_priority=0.44,
            generated_at=datetime.utcnow()
        ).prefix_with('OR IGNORE'))
        await postgres_session.execute(insert(AlertDelivery).values(
            alert_id=9999, recipient_phone='+254700000099',
            at_message_id='test-msg-id', status='Success',
            dispatched_at=datetime.utcnow()
        ).prefix_with('OR IGNORE'))
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
                AlertResponse.alert_id == 9999,
                AlertResponse.response == 'Y'
            )
        )
        assert result.scalar_one_or_none() is not None