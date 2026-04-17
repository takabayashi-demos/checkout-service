"""Security tests for checkout-service."""
import pytest
import json
from app import app, validate_integer, validate_coupon_code, validate_coupon_data


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class TestInputValidation:
    """Test input validation functions."""

    def test_validate_integer_valid(self):
        assert validate_integer("42", "test") == 42
        assert validate_integer("0", "test", min_val=0) == 0
        assert validate_integer("100", "test", max_val=100) == 100

    def test_validate_integer_invalid(self):
        with pytest.raises(ValueError, match="Invalid test"):
            validate_integer("abc", "test")
        with pytest.raises(ValueError, match="must be between"):
            validate_integer("-1", "test", min_val=0)
        with pytest.raises(ValueError, match="must be between"):
            validate_integer("10001", "test", max_val=10000)

    def test_validate_coupon_code_valid(self):
        assert validate_coupon_code("SAVE20") == "SAVE20"
        assert validate_coupon_code("WINTER-2024") == "WINTER-2024"
        assert validate_coupon_code("CODE_123") == "CODE_123"

    def test_validate_coupon_code_invalid(self):
        with pytest.raises(ValueError, match="must be a string"):
            validate_coupon_code(123)
        with pytest.raises(ValueError, match="must be 3-50 characters"):
            validate_coupon_code("AB")
        with pytest.raises(ValueError, match="invalid characters"):
            validate_coupon_code("save20<script>")
        with pytest.raises(ValueError, match="invalid characters"):
            validate_coupon_code("DROP TABLE coupons;--")

    def test_validate_coupon_data_valid(self):
        data = {
            "code": "SAVE20",
            "name": "20% off",
            "value": 20,
            "active": True
        }
        result = validate_coupon_data(data)
        assert result["code"] == "SAVE20"
        assert result["value"] == 20
        assert result["active"] is True

    def test_validate_coupon_data_missing_fields(self):
        with pytest.raises(ValueError, match="Missing required field"):
            validate_coupon_data({"code": "TEST"})

    def test_validate_coupon_data_sanitization(self):
        data = {
            "code": "SAVE20",
            "name": "x" * 300,
            "value": 20
        }
        result = validate_coupon_data(data)
        assert len(result["name"]) == 200


class TestEndpointSecurity:
    """Test endpoint security measures."""

    def test_list_coupons_invalid_limit(self, client):
        response = client.get("/api/v1/coupon?limit=abc")
        assert response.status_code == 400
        assert b"error" in response.data

    def test_list_coupons_limit_overflow(self, client):
        response = client.get("/api/v1/coupon?limit=999999")
        assert response.status_code == 400

    def test_list_coupons_negative_offset(self, client):
        response = client.get("/api/v1/coupon?offset=-1")
        assert response.status_code == 400

    def test_get_coupon_invalid_id(self, client):
        response = client.get("/api/v1/coupon/abc")
        assert response.status_code == 400

    def test_get_coupon_sql_injection_attempt(self, client):
        response = client.get("/api/v1/coupon/1' OR '1'='1")
        assert response.status_code == 400

    def test_create_coupon_invalid_json(self, client):
        response = client.post(
            "/api/v1/coupon",
            data="not json",
            content_type="text/plain"
        )
        assert response.status_code == 400

    def test_create_coupon_xss_attempt(self, client):
        response = client.post(
            "/api/v1/coupon",
            data=json.dumps({
                "code": "<script>alert('xss')</script>",
                "name": "Test",
                "value": 10
            }),
            content_type="application/json"
        )
        assert response.status_code == 400
        assert b"invalid characters" in response.data

    def test_create_coupon_sql_injection_attempt(self, client):
        response = client.post(
            "/api/v1/coupon",
            data=json.dumps({
                "code": "'; DROP TABLE coupons;--",
                "name": "Test",
                "value": 10
            }),
            content_type="application/json"
        )
        assert response.status_code == 400

    def test_health_endpoint_exempt_from_rate_limit(self, client):
        # Health check should always work regardless of rate limits
        for _ in range(200):
            response = client.get("/health")
            assert response.status_code == 200
