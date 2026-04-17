"""Tests for checkout-service."""
import pytest
import json
from app import app, parse_int_param


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class TestParseIntParam:
    """Test the parse_int_param helper function."""

    def test_returns_default_when_none(self):
        assert parse_int_param(None, default=10) == 10

    def test_parses_valid_integer(self):
        assert parse_int_param("42", default=10) == 42

    def test_rejects_non_integer(self):
        with pytest.raises(ValueError, match="Invalid integer value"):
            parse_int_param("abc", default=10)

    def test_rejects_negative_when_min_is_zero(self):
        with pytest.raises(ValueError, match="must be at least 0"):
            parse_int_param("-5", default=10, min_val=0)

    def test_rejects_value_above_max(self):
        with pytest.raises(ValueError, match="must not exceed 100"):
            parse_int_param("150", default=10, max_val=100)

    def test_accepts_value_at_max(self):
        assert parse_int_param("100", default=10, max_val=100) == 100

    def test_accepts_value_at_min(self):
        assert parse_int_param("0", default=10, min_val=0) == 0


class TestListCoupons:
    """Test the /api/v1/coupon GET endpoint."""

    def test_rejects_non_numeric_limit(self, client):
        response = client.get("/api/v1/coupon?limit=abc")
        assert response.status_code == 400
        data = json.loads(response.data)
        assert "error" in data
        assert "Invalid integer value" in data["error"]

    def test_rejects_non_numeric_offset(self, client):
        response = client.get("/api/v1/coupon?offset=xyz")
        assert response.status_code == 400
        data = json.loads(response.data)
        assert "error" in data

    def test_rejects_negative_offset(self, client):
        response = client.get("/api/v1/coupon?offset=-10")
        assert response.status_code == 400
        data = json.loads(response.data)
        assert "must be at least 0" in data["error"]

    def test_rejects_limit_above_100(self, client):
        response = client.get("/api/v1/coupon?limit=200")
        assert response.status_code == 400
        data = json.loads(response.data)
        assert "must not exceed 100" in data["error"]

    def test_rejects_zero_limit(self, client):
        response = client.get("/api/v1/coupon?limit=0")
        assert response.status_code == 400
        data = json.loads(response.data)
        assert "must be at least 1" in data["error"]

    def test_accepts_valid_pagination_params(self, client):
        # This will fail at DB connection in test env, but validates
        # parameter parsing succeeds
        response = client.get("/api/v1/coupon?limit=50&offset=10")
        # 200 if DB available, 500 if not — either way, not 400
        assert response.status_code != 400
