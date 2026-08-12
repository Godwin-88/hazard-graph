"""HazardGraph — DataHub + Agent API integration tests.

These tests require the Docker test containers (docker-compose.test.yml).
They verify the new DataHub and agent endpoints work with authentication.
"""

import pytest


class TestDataHubEndpoints:
    @pytest.mark.asyncio
    async def test_lineage_endpoint_requires_auth(self, api_client):
        response = await api_client.get('/api/v1/datahub/lineage/alert-123')
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_lineage_endpoint_returns_chain(self, api_client, auth_headers):
        response = await api_client.get(
            '/api/v1/datahub/lineage/alert-123',
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data['alert_id'] == 'alert-123'
        assert len(data['lineage_chain']) == 8

    @pytest.mark.asyncio
    async def test_model_health_endpoint(self, api_client, auth_headers):
        response = await api_client.get(
            '/api/v1/datahub/model-health',
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data['models']) == 14
        for model in data['models']:
            assert model['id']
            assert model['name']
            assert model['datahub_urn']

    @pytest.mark.asyncio
    async def test_pipeline_freshness_endpoint(self, api_client, auth_headers):
        response = await api_client.get(
            '/api/v1/datahub/pipeline-freshness',
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert 'datasets' in data
        # All 5 upstream datasets should be present
        assert len(data['datasets']) == 5


class TestAgentEndpoints:
    @pytest.mark.asyncio
    async def test_agent_query_requires_auth(self, api_client):
        response = await api_client.post('/api/v1/agent/query', json={'query': 'test'})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_agent_query_returns_response(self, api_client, auth_headers):
        response = await api_client.post(
            '/api/v1/agent/query',
            json={
                'query': 'Why was the Mandera alert dispatched this week?',
                'alert_id': 'alert-123',
            },
            headers=auth_headers,
        )
        # The agent may fail if GROQ isn't configured, but should still
        # return a structured response with context
        assert response.status_code in (200, 502)
        if response.status_code == 200:
            data = response.json()
            assert 'response' in data
            assert 'context_used' in data
            assert 'freshness' in data
            assert 'model_health' in data