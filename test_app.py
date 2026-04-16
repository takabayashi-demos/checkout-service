"""Tests for coupon in checkout-service."""
import pytest
import time
import json
from unittest.mock import patch, MagicMock


@pytest.fixture
def client():
    """Create a test client with mocked DB and cache."""
    # Patch Redis before importing app so connection doesn't fail.
    with patch("app.cache", None):
        from app import app
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c


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
        payload = {"name": "test", "value": 42}
        response = client.post("/api/v1/coupon", json=payload)
        assert response.status_code in (200, 201)

    def test_coupon_validation(self, client):
        """Should reject invalid coupon data."""
        response = client.post("/api/v1/coupon", json={})
        assert response.status_code in (400, 422)

    def test_coupon_not_found(self, client):
        """Should return 404 for missing coupon."""
        response = client.get("/api/v1/coupon/nonexistent")
        assert response.status_code == 404

    @pytest.mark.parametrize("limit", [1, 10, 50, 100])
    def test_coupon_pagination(self, client, limit):
        """Should respect pagination limits."""
        response = client.get(f"/api/v1/coupon?limit={limit}")
        assert response.status_code == 200
        data = response.get_json()
        assert len(data.get("items", data.get("coupons", []))) <= limit

    def test_coupon_performance(self, client):
        """Response time should be under 500ms."""
        start = time.monotonic()
        response = client.get("/api/v1/coupon")
        elapsed = time.monotonic() - start
        assert elapsed < 0.5, f"Took {elapsed:.2f}s, expected <0.5s"


class TestCouponCaching:
    """Tests for the Redis caching layer."""

    def test_cache_hit_returns_cached_data(self):
        """GET /coupon/<id> should return cached data without hitting DB."""
        cached_coupon = {"id": 1, "code": "SAVE10", "name": "Save 10", "value": 10, "active": True}
        mock_cache = MagicMock()
        mock_cache.get.return_value = json.dumps(cached_coupon)

        with patch("app.cache", mock_cache):
            from app import app
            app.config["TESTING"] = True
            with app.test_client() as c:
                response = c.get("/api/v1/coupon/1")

        assert response.status_code == 200
        data = response.get_json()
        assert data["code"] == "SAVE10"

    def test_cache_miss_falls_through_to_db(self):
        """When cache misses, the request should still succeed via DB."""
        mock_cache = MagicMock()
        mock_cache.get.return_value = None

        with patch("app.cache", mock_cache):
            from app import app
            app.config["TESTING"] = True
            with app.test_client() as c:
                response = c.get("/api/v1/coupon/nonexistent")

        # Should still work (404 because coupon doesn't exist, not 500)
        assert response.status_code == 404

    def test_cache_failure_degrades_gracefully(self):
        """If Redis throws, requests should still work via DB."""
        import redis as redis_mod
        mock_cache = MagicMock()
        mock_cache.get.side_effect = redis_mod.RedisError("connection lost")

        with patch("app.cache", mock_cache):
            from app import app
            app.config["TESTING"] = True
            with app.test_client() as c:
                response = c.get("/api/v1/coupon/1")

        # Should degrade to DB path, not crash
        assert response.status_code in (200, 404)

    def test_create_invalidates_list_cache(self):
        """POST /coupon should invalidate the list cache."""
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        mock_cache.keys.return_value = ["coupons:list:20:0"]

        with patch("app.cache", mock_cache):
            from app import app
            app.config["TESTING"] = True
            with app.test_client() as c:
                c.post("/api/v1/coupon", json={"name": "new", "value": 15})

        mock_cache.keys.assert_called_with("coupons:list:*")
        mock_cache.delete.assert_called_once()
