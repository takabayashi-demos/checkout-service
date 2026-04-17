"""Tests for checkout-service coupon endpoints."""
import pytest
import json
from app import app, cache


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear cache before each test."""
    if cache:
        cache.flushdb()
    yield
    if cache:
        cache.flushdb()


class TestCouponValidation:
    """Test input validation for coupon endpoints."""

    def test_create_coupon_missing_code(self, client):
        response = client.post(
            "/api/v1/coupon",
            data=json.dumps({"name": "Test Coupon", "value": 10.0}),
            content_type="application/json",
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert "code" in data["error"].lower()

    def test_create_coupon_missing_name(self, client):
        response = client.post(
            "/api/v1/coupon",
            data=json.dumps({"code": "TEST10", "value": 10.0}),
            content_type="application/json",
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert "name" in data["error"].lower()

    def test_create_coupon_missing_value(self, client):
        response = client.post(
            "/api/v1/coupon",
            data=json.dumps({"code": "TEST10", "name": "Test Coupon"}),
            content_type="application/json",
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert "value" in data["error"].lower()

    def test_create_coupon_empty_code(self, client):
        response = client.post(
            "/api/v1/coupon",
            data=json.dumps({"code": "  ", "name": "Test", "value": 10.0}),
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_create_coupon_invalid_value_type(self, client):
        response = client.post(
            "/api/v1/coupon",
            data=json.dumps({"code": "TEST10", "name": "Test", "value": "invalid"}),
            content_type="application/json",
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert "valid number" in data["error"].lower()

    def test_create_coupon_negative_value(self, client):
        response = client.post(
            "/api/v1/coupon",
            data=json.dumps({"code": "TEST10", "name": "Test", "value": -5.0}),
            content_type="application/json",
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert "greater than 0" in data["error"].lower()

    def test_create_coupon_zero_value(self, client):
        response = client.post(
            "/api/v1/coupon",
            data=json.dumps({"code": "TEST10", "name": "Test", "value": 0}),
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_create_coupon_empty_body(self, client):
        response = client.post(
            "/api/v1/coupon",
            data="",
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_update_coupon_invalid_value(self, client):
        response = client.put(
            "/api/v1/coupon/1",
            data=json.dumps({"value": -10.0}),
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_update_coupon_empty_body(self, client):
        response = client.put(
            "/api/v1/coupon/1",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert "at least one field" in data["error"].lower()
