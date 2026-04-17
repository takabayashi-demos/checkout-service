"""Tests for checkout-service security validations."""
import pytest
import json
from app import app, validate_coupon_code, validate_coupon_input


@pytest.fixture
def client():
    """Test client fixture."""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


class TestCouponCodeValidation:
    """Test coupon code validation."""
    
    def test_valid_codes(self):
        assert validate_coupon_code("SUMMER2024")
        assert validate_coupon_code("SAVE_20")
        assert validate_coupon_code("black-friday")
        assert validate_coupon_code("ABC123")
    
    def test_invalid_codes(self):
        assert not validate_coupon_code("")
        assert not validate_coupon_code(None)
        assert not validate_coupon_code(123)
        assert not validate_coupon_code("a" * 51)
        assert not validate_coupon_code("SAVE 20")
        assert not validate_coupon_code("SAVE@20")
        assert not validate_coupon_code("DROP TABLE coupons--")
        assert not validate_coupon_code("<script>alert('xss')</script>")


class TestCouponInputValidation:
    """Test full coupon input validation."""
    
    def test_valid_input(self):
        data = {
            "code": "SAVE20",
            "name": "Summer Sale",
            "value": 20.0,
            "active": True
        }
        assert validate_coupon_input(data) == []
    
    def test_missing_required_fields(self):
        errors = validate_coupon_input({})
        assert "code is required" in errors
        assert "name is required" in errors
        assert "value is required" in errors
    
    def test_invalid_code(self):
        data = {
            "code": "SAVE 20!",
            "name": "Summer Sale",
            "value": 20.0
        }
        errors = validate_coupon_input(data)
        assert any("code must be alphanumeric" in e for e in errors)
    
    def test_invalid_name(self):
        data = {
            "code": "SAVE20",
            "name": "x" * 201,
            "value": 20.0
        }
        errors = validate_coupon_input(data)
        assert any("name must be a string" in e for e in errors)
    
    def test_invalid_value(self):
        data = {
            "code": "SAVE20",
            "name": "Summer Sale",
            "value": -10
        }
        errors = validate_coupon_input(data)
        assert any("value must be a non-negative number" in e for e in errors)
    
    def test_invalid_active(self):
        data = {
            "code": "SAVE20",
            "name": "Summer Sale",
            "value": 20.0,
            "active": "yes"
        }
        errors = validate_coupon_input(data)
        assert any("active must be a boolean" in e for e in errors)


class TestCreateCouponEndpoint:
    """Test POST /api/v1/coupon security."""
    
    def test_rejects_non_json(self, client):
        response = client.post('/api/v1/coupon', data="not json")
        assert response.status_code == 400
        assert b"application/json" in response.data
    
    def test_rejects_invalid_code(self, client):
        data = {
            "code": "'; DROP TABLE coupons; --",
            "name": "Malicious",
            "value": 10
        }
        response = client.post('/api/v1/coupon',
                               data=json.dumps(data),
                               content_type='application/json')
        assert response.status_code == 400
        result = json.loads(response.data)
        assert result["error"] == "validation failed"
    
    def test_rejects_xss_attempt(self, client):
        data = {
            "code": "SAVE20",
            "name": "<script>alert('xss')</script>",
            "value": 10
        }
        response = client.post('/api/v1/coupon',
                               data=json.dumps(data),
                               content_type='application/json')
        assert response.status_code == 400
    
    def test_rejects_oversized_input(self, client):
        data = {
            "code": "A" * 51,
            "name": "Valid Name",
            "value": 10
        }
        response = client.post('/api/v1/coupon',
                               data=json.dumps(data),
                               content_type='application/json')
        assert response.status_code == 400
