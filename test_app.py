"""Tests for checkout-service."""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from app import app, cache_delete


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_cache_delete_uses_scan_iter():
    """Verify cache_delete uses non-blocking scan_iter instead of keys."""
    mock_cache = Mock()
    mock_cache.scan_iter.return_value = iter(["coupons:list:20:0", "coupons:list:20:20", "coupons:list:50:0"])
    
    with patch("app.cache", mock_cache):
        cache_delete("coupons:list:*")
    
    mock_cache.scan_iter.assert_called_once_with(match="coupons:list:*", count=100)
    mock_cache.delete.assert_called_once_with("coupons:list:20:0", "coupons:list:20:20", "coupons:list:50:0")


def test_cache_delete_handles_empty_results():
    """Verify cache_delete handles no matching keys gracefully."""
    mock_cache = Mock()
    mock_cache.scan_iter.return_value = iter([])
    
    with patch("app.cache", mock_cache):
        cache_delete("coupons:list:*")
    
    mock_cache.delete.assert_not_called()


def test_cache_delete_handles_redis_error():
    """Verify cache_delete doesn't crash on Redis errors."""
    mock_cache = Mock()
    mock_cache.scan_iter.side_effect = Exception("Redis connection failed")
    
    with patch("app.cache", mock_cache):
        cache_delete("coupons:list:*")


def test_create_coupon_invalidates_list_cache(client):
    """Verify creating a coupon invalidates list cache."""
    mock_cache = Mock()
    mock_cache.scan_iter.return_value = iter(["coupons:list:20:0"])
    
    mock_conn = MagicMock()
    mock_result = Mock()
    mock_result.fetchone.return_value = [123]
    mock_conn.__enter__.return_value.execute.return_value = mock_result
    
    with patch("app.cache", mock_cache), patch("app.get_db", return_value=mock_conn):
        response = client.post(
            "/api/v1/coupon",
            data=json.dumps({"code": "SAVE20", "name": "20% off", "value": 20}),
            content_type="application/json",
        )
    
    assert response.status_code == 201
    mock_cache.scan_iter.assert_called_with(match="coupons:list:*", count=100)
