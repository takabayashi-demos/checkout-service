"""Test suite for checkout-service."""
import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from sqlalchemy.engine import Row
from app import app, cache_get, cache_set, cache_delete


@pytest.fixture
def client():
    """Flask test client."""
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def mock_db_conn():
    """Mock database connection."""
    conn = MagicMock()
    conn.__enter__ = Mock(return_value=conn)
    conn.__exit__ = Mock(return_value=False)
    return conn


@pytest.fixture
def mock_redis():
    """Mock Redis cache."""
    with patch("app.cache") as mock:
        yield mock


class TestHealth:
    """Health endpoint tests."""

    def test_health_with_cache(self, client, mock_redis):
        mock_redis.__bool__ = Mock(return_value=True)
        response = client.get("/health")
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "UP"
        assert data["service"] == "checkout-service"
        assert data["cache"] == "UP"

    def test_health_without_cache(self, client):
        with patch("app.cache", None):
            response = client.get("/health")
            assert response.status_code == 200
            data = response.get_json()
            assert data["status"] == "UP"
            assert data["cache"] == "DEGRADED"


class TestListCoupons:
    """Coupon listing endpoint tests."""

    def test_list_coupons_cache_hit(self, client, mock_redis):
        cached_data = {
            "items": [{"id": 1, "code": "SAVE10", "name": "10% Off", "value": 10, "active": True}],
            "limit": 20,
            "offset": 0,
        }
        mock_redis.get.return_value = json.dumps(cached_data)

        response = client.get("/api/v1/coupon")
        assert response.status_code == 200
        assert response.get_json() == cached_data
        mock_redis.get.assert_called_once_with("coupons:list:20:0")

    def test_list_coupons_cache_miss(self, client, mock_redis, mock_db_conn):
        mock_redis.get.return_value = None
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row._mapping = {"id": 1, "code": "SAVE10", "name": "10% Off", "value": 10, "active": True}
        mock_result.__iter__ = Mock(return_value=iter([mock_row]))
        mock_db_conn.execute.return_value = mock_result

        with patch("app.get_db", return_value=mock_db_conn):
            response = client.get("/api/v1/coupon")

        assert response.status_code == 200
        data = response.get_json()
        assert len(data["items"]) == 1
        assert data["items"][0]["code"] == "SAVE10"
        assert data["limit"] == 20
        assert data["offset"] == 0

    def test_list_coupons_custom_pagination(self, client, mock_redis, mock_db_conn):
        mock_redis.get.return_value = None
        mock_db_conn.execute.return_value = MagicMock(__iter__=Mock(return_value=iter([])))

        with patch("app.get_db", return_value=mock_db_conn):
            response = client.get("/api/v1/coupon?limit=50&offset=100")

        assert response.status_code == 200
        data = response.get_json()
        assert data["limit"] == 50
        assert data["offset"] == 100
        mock_db_conn.execute.assert_called_once()
        call_args = mock_db_conn.execute.call_args
        assert call_args[1]["limit"] == 50
        assert call_args[1]["offset"] == 100

    def test_list_coupons_limit_cap(self, client, mock_redis, mock_db_conn):
        """Limit should be capped at 100 even if higher value requested."""
        mock_redis.get.return_value = None
        mock_db_conn.execute.return_value = MagicMock(__iter__=Mock(return_value=iter([])))

        with patch("app.get_db", return_value=mock_db_conn):
            response = client.get("/api/v1/coupon?limit=500")

        assert response.status_code == 200
        data = response.get_json()
        assert data["limit"] == 100


class TestGetCoupon:
    """Single coupon retrieval tests."""

    def test_get_coupon_cache_hit(self, client, mock_redis):
        cached_coupon = {"id": 42, "code": "FLASH50", "name": "Flash Sale", "value": 50, "active": True}
        mock_redis.get.return_value = json.dumps(cached_coupon)

        response = client.get("/api/v1/coupon/42")
        assert response.status_code == 200
        assert response.get_json() == cached_coupon
        mock_redis.get.assert_called_once_with("coupons:id:42")

    def test_get_coupon_cache_miss(self, client, mock_redis, mock_db_conn):
        mock_redis.get.return_value = None
        mock_row = MagicMock()
        mock_row._mapping = {"id": 42, "code": "FLASH50", "name": "Flash Sale", "value": 50, "active": True}
        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        mock_db_conn.execute.return_value = mock_result

        with patch("app.get_db", return_value=mock_db_conn):
            response = client.get("/api/v1/coupon/42")

        assert response.status_code == 200
        data = response.get_json()
        assert data["id"] == 42
        assert data["code"] == "FLASH50"

    def test_get_coupon_not_found(self, client, mock_redis, mock_db_conn):
        mock_redis.get.return_value = None
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_db_conn.execute.return_value = mock_result

        with patch("app.get_db", return_value=mock_db_conn):
            response = client.get("/api/v1/coupon/99999")

        assert response.status_code == 404
        data = response.get_json()
        assert "error" in data
        assert data["error"] == "coupon not found"


class TestCacheHelpers:
    """Cache utility function tests."""

    def test_cache_get_success(self, mock_redis):
        test_data = {"key": "value"}
        mock_redis.get.return_value = json.dumps(test_data)

        with patch("app.cache", mock_redis):
            result = cache_get("test_key")

        assert result == test_data
        mock_redis.get.assert_called_once_with("test_key")

    def test_cache_get_miss(self, mock_redis):
        mock_redis.get.return_value = None

        with patch("app.cache", mock_redis):
            result = cache_get("missing_key")

        assert result is None

    def test_cache_get_no_cache(self):
        with patch("app.cache", None):
            result = cache_get("any_key")

        assert result is None

    def test_cache_get_redis_error(self, mock_redis):
        import redis
        mock_redis.get.side_effect = redis.RedisError("Connection failed")

        with patch("app.cache", mock_redis):
            result = cache_get("error_key")

        assert result is None

    def test_cache_set_success(self, mock_redis):
        test_data = {"key": "value"}

        with patch("app.cache", mock_redis):
            cache_set("test_key", test_data, ttl=120)

        mock_redis.setex.assert_called_once_with("test_key", 120, json.dumps(test_data))

    def test_cache_set_no_cache(self):
        with patch("app.cache", None):
            cache_set("any_key", {"data": "value"})

    def test_cache_set_redis_error(self, mock_redis):
        import redis
        mock_redis.setex.side_effect = redis.RedisError("Write failed")

        with patch("app.cache", mock_redis):
            cache_set("error_key", {"data": "value"})

    def test_cache_delete_success(self, mock_redis):
        mock_redis.keys.return_value = ["coupons:id:1", "coupons:id:2"]

        with patch("app.cache", mock_redis):
            cache_delete("coupons:id:*")

        mock_redis.keys.assert_called_once_with("coupons:id:*")
        mock_redis.delete.assert_called_once_with("coupons:id:1", "coupons:id:2")

    def test_cache_delete_no_keys(self, mock_redis):
        mock_redis.keys.return_value = []

        with patch("app.cache", mock_redis):
            cache_delete("coupons:id:*")

        mock_redis.keys.assert_called_once()
        mock_redis.delete.assert_not_called()

    def test_cache_delete_no_cache(self):
        with patch("app.cache", None):
            cache_delete("any:pattern:*")
