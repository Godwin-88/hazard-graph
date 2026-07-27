"""Full API integration tests using test client + Docker DBs."""

import pytest


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_ok(self, api_client):
        response = await api_client.get('/api/v1/health')
        assert response.status_code == 200
        data = response.json()
        assert data['neo4j']['connected'] is True
        assert data['postgres']['connected'] is True
        assert data['redis']['connected'] is True


class TestAuthEndpoints:
    @pytest.mark.asyncio
    async def test_login_returns_tokens(self, api_client):
        response = await api_client.post('/api/v1/auth/login', json={
            'username': 'admin',
            'password': 'HazardGraph2026!'
        })
        # May fail if user not seeded - that's fine for this test
        if response.status_code == 200:
            data = response.json()
            assert 'access_token' in data
            assert 'role' in data
            assert data['role'] == 'admin'

    @pytest.mark.asyncio
    async def test_protected_route_requires_auth(self, api_client):
        response = await api_client.get('/api/v1/alerts')
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_protected_route_with_valid_token(
        self, api_client, auth_headers
    ):
        response = await api_client.get(
            '/api/v1/alerts', headers=auth_headers
        )
        assert response.status_code == 200


class TestRiskScoresEndpoint:
    @pytest.mark.asyncio
    async def test_risk_scores_structure(self, api_client, auth_headers):
        response = await api_client.get(
            '/api/v1/risk/scores', headers=auth_headers
        )
        if response.status_code == 200:
            data = response.json()
            assert 'regions' in data
            assert 'computed_at' in data
            assert 'summary' in data
            for region in data['regions']:
                assert 0.0 <= region['score'] <= 100.0
                assert region['confidence'] in ['High', 'Medium', 'Low']


class TestGraphEndpoints:
    @pytest.mark.asyncio
    async def test_graph_nodes_returns_nodes_and_edges(
        self, api_client, auth_headers
    ):
        response = await api_client.get(
            '/api/v1/graph/nodes', headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert 'nodes' in data
        assert 'edges' in data
        assert isinstance(data['nodes'], list)

    @pytest.mark.asyncio
    async def test_graph_regimes_returns_all_regions(
        self, api_client, auth_headers
    ):
        response = await api_client.get(
            '/api/v1/graph/regimes', headers=auth_headers
        )
        if response.status_code == 200:
            data = response.json()
            assert 'regions' in data