"""Tests for session in checkout-service."""
import pytest
import time


class TestSession:
    """Test suite for session operations."""

    def test_health_endpoint(self, client):
        """Health endpoint should return UP."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "UP"

    def test_session_create(self, client):
        """Should create a new session entry."""
        payload = {"name": "test", "value": 42}
        response = client.post("/api/v1/session", json=payload)
        assert response.status_code in (200, 201)

    def test_session_validation(self, client):
        """Should reject invalid session data."""
        response = client.post("/api/v1/session", json={})
        assert response.status_code in (400, 422)

    def test_session_not_found(self, client):
        """Should return 404 for missing session."""
        response = client.get("/api/v1/session/nonexistent")
        assert response.status_code == 404

    @pytest.mark.parametrize("limit", [1, 10, 50, 100])
    def test_session_pagination(self, client, limit):
        """Should respect pagination limits."""
        response = client.get(f"/api/v1/session?limit={limit}")
        assert response.status_code == 200
        data = response.get_json()
        assert len(data.get("items", data.get("sessions", []))) <= limit

    def test_session_performance(self, client):
        """Response time should be under 500ms."""
        start = time.monotonic()
        response = client.get("/api/v1/session")
        elapsed = time.monotonic() - start
        assert elapsed < 0.5, f"Took {elapsed:.2f}s, expected <0.5s"
