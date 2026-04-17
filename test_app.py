"""Tests for checkout-service."""
import pytest
import json
from unittest.mock import MagicMock, patch
from app import app, cache_get, cache_set


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def mock_db():
    with patch("app.get_db") as mock:
        yield mock


@pytest.fixture
def mock_cache():
    with patch("app.cache") as mock:
        yield mock


class TestValidateCoupon:
    def test_validate_coupon_success(self, client, mock_db, mock_cache):
        """Valid active coupon returns coupon data."""
        mock_cache.get.return_value = None
        
        mock_conn = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_conn
        
        mock_row = MagicMock()
        mock_row._mapping = {
            "id": 1,
            "code": "SAVE20",
            "name": "20% Off",
            "value": 20.0,
            "active": True,
        }
        mock_conn.execute.return_value.fetchone.return_value = mock_row

        response = client.get("/api/v1/coupon/validate?code=SAVE20")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["code"] == "SAVE20"
        assert data["value"] == 20.0
        assert data["active"] is True

    def test_validate_coupon_missing_code(self, client):
        """Missing code parameter returns 400."""
        response = client.get("/api/v1/coupon/validate")
        assert response.status_code == 400
        data = json.loads(response.data)
        assert "code parameter required" in data["error"]

    def test_validate_coupon_not_found(self, client, mock_db, mock_cache):
        """Invalid or inactive coupon returns 404."""
        mock_cache.get.return_value = None
        
        mock_conn = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchone.return_value = None

        response = client.get("/api/v1/coupon/validate?code=INVALID")
        assert response.status_code == 404
        data = json.loads(response.data)
        assert "invalid or inactive" in data["error"]

    def test_validate_coupon_cached(self, client, mock_cache):
        """Cached coupon is returned without database query."""
        cached_data = {
            "id": 1,
            "code": "SAVE20",
            "name": "20% Off",
            "value": 20.0,
            "active": True,
        }
        mock_cache.get.return_value = json.dumps(cached_data)

        with patch("app.get_db") as mock_db:
            response = client.get("/api/v1/coupon/validate?code=SAVE20")
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data["code"] == "SAVE20"
            mock_db.assert_not_called()


class TestHealth:
    def test_health_endpoint(self, client):
        """Health check returns service status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "UP"
        assert data["service"] == "checkout-service"
