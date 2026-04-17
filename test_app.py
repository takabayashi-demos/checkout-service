"""Tests for checkout-service cache invalidation."""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from app import app, cache_delete


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_cache_delete_uses_scan_not_keys():
    """Verify cache_delete uses SCAN instead of blocking KEYS command."""
    mock_cache = Mock()
    mock_cache.scan_iter.return_value = iter(["coupons:id:1", "coupons:id:2"])
    
    with patch("app.cache", mock_cache):
        cache_delete("coupons:*")
    
    mock_cache.scan_iter.assert_called_once_with(match="coupons:*", count=100)
    assert mock_cache.delete.call_count == 2
    assert not mock_cache.keys.called


def test_create_coupon_invalidates_cache(client):
    """Verify coupon creation invalidates all coupon caches."""
    mock_cache = Mock()
    mock_cache.scan_iter.return_value = iter(["coupons:list:20:0", "coupons:id:5"])
    
    with patch("app.cache", mock_cache), \
         patch("app.get_db") as mock_db:
        
        mock_conn = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchone.return_value = [123]
        mock_db.return_value = mock_conn
        
        response = client.post(
            "/api/v1/coupon",
            data=json.dumps({"code": "SAVE20", "name": "20% Off", "value": 20}),
            content_type="application/json"
        )
        
        assert response.status_code == 201
        mock_cache.scan_iter.assert_called_with(match="coupons:*", count=100)


def test_update_coupon_invalidates_cache(client):
    """Verify coupon updates invalidate all coupon caches."""
    mock_cache = Mock()
    mock_cache.scan_iter.return_value = iter(["coupons:id:1"])
    
    with patch("app.cache", mock_cache), \
         patch("app.get_db") as mock_db:
        
        mock_conn = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_result = Mock()
        mock_result.rowcount = 1
        mock_conn.execute.return_value = mock_result
        mock_db.return_value = mock_conn
        
        response = client.put(
            "/api/v1/coupon/1",
            data=json.dumps({"code": "SAVE30", "name": "30% Off", "value": 30}),
            content_type="application/json"
        )
        
        assert response.status_code == 200
        mock_cache.scan_iter.assert_called_with(match="coupons:*", count=100)
