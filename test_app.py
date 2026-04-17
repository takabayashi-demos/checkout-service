"""Tests for checkout-service."""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
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
    with patch("app.cache_get") as get_mock, patch("app.cache_set") as set_mock:
        yield {"get": get_mock, "set": set_mock}


class TestCouponValidation:
    def test_validate_coupon_success(self, client, mock_db, mock_cache):
        """Valid active coupon returns discount calculation."""
        mock_cache["get"].return_value = None

        mock_result = Mock()
        mock_row = Mock()
        mock_row._mapping = {
            "id": 1,
            "code": "SAVE20",
            "name": "Save $20",
            "value": 20.0,
            "active": True,
        }
        mock_result.fetchone.return_value = mock_row

        mock_conn = MagicMock()
        mock_conn.__enter__.return_value.execute.return_value = mock_result
        mock_db.return_value = mock_conn

        response = client.post(
            "/api/v1/coupon/validate",
            data=json.dumps({"code": "SAVE20", "cart_total": 100.0}),
            content_type="application/json",
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["valid"] is True
        assert data["discount_amount"] == 20.0
        assert data["final_total"] == 80.0
        assert data["coupon_code"] == "SAVE20"

    def test_validate_coupon_not_found(self, client, mock_db, mock_cache):
        """Non-existent coupon returns invalid."""
        mock_cache["get"].return_value = None

        mock_result = Mock()
        mock_result.fetchone.return_value = None

        mock_conn = MagicMock()
        mock_conn.__enter__.return_value.execute.return_value = mock_result
        mock_db.return_value = mock_conn

        response = client.post(
            "/api/v1/coupon/validate",
            data=json.dumps({"code": "INVALID", "cart_total": 100.0}),
            content_type="application/json",
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["valid"] is False
        assert data["message"] == "coupon not found"

    def test_validate_coupon_inactive(self, client, mock_cache):
        """Inactive coupon returns invalid."""
        mock_cache["get"].return_value = {
            "id": 2,
            "code": "EXPIRED",
            "name": "Expired coupon",
            "value": 10.0,
            "active": False,
        }

        response = client.post(
            "/api/v1/coupon/validate",
            data=json.dumps({"code": "EXPIRED", "cart_total": 50.0}),
            content_type="application/json",
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["valid"] is False
        assert data["message"] == "coupon is inactive"

    def test_validate_coupon_missing_fields(self, client):
        """Missing required fields returns 400."""
        response = client.post(
            "/api/v1/coupon/validate",
            data=json.dumps({"code": "TEST"}),
            content_type="application/json",
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert "error" in data

    def test_validate_coupon_case_insensitive(self, client, mock_db, mock_cache):
        """Coupon codes are case-insensitive."""
        mock_cache["get"].return_value = None

        mock_result = Mock()
        mock_row = Mock()
        mock_row._mapping = {
            "id": 3,
            "code": "WELCOME10",
            "name": "Welcome offer",
            "value": 10.0,
            "active": True,
        }
        mock_result.fetchone.return_value = mock_row

        mock_conn = MagicMock()
        mock_conn.__enter__.return_value.execute.return_value = mock_result
        mock_db.return_value = mock_conn

        response = client.post(
            "/api/v1/coupon/validate",
            data=json.dumps({"code": "welcome10", "cart_total": 25.0}),
            content_type="application/json",
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["valid"] is True
        assert data["coupon_code"] == "WELCOME10"
