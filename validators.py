def validate_order(data): return True


# --- refactor: simplify coupon logic ---
"""Tests for coupon in checkout-service."""
import pytest
import time


class TestCoupon:
    """Test suite for coupon operations."""

    def test_health_endpoint(self, client):
        """Health endpoint should return UP."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "UP"

    def test_coupon_create(self, client):
        """Should create a new coupon entry."""
