"""Tests for checkout-service coupon cache invalidation."""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from app import app, cache_delete


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def mock_db():
    with patch("app.get_db") as mock:
        conn = MagicMock()
        mock.return_value.__enter__ = Mock(return_value=conn)
        mock.return_value.__exit__ = Mock(return_value=False)
        yield conn


@pytest.fixture
def mock_cache():
    with patch("app.cache") as mock:
        mock.get.return_value = None
        mock.keys.return_value = []
        yield mock


def test_create_coupon_invalidates_cache(client, mock_db, mock_cache):
    """Creating a coupon should invalidate list and detail caches."""
    mock_result = Mock()
    mock_result.fetchone.return_value = [123]
    mock_db.execute.return_value = mock_result

    response = client.post(
        "/api/v1/coupon",
        data=json.dumps({"code": "SAVE20", "name": "20% Off", "value": 20}),
        content_type="application/json",
    )

    assert response.status_code == 201
    assert mock_cache.keys.call_count >= 1
    assert any(
        "coupons:list:" in str(call) for call in mock_cache.keys.call_args_list
    )


def test_update_coupon_invalidates_cache(client, mock_db, mock_cache):
    """Updating a coupon should invalidate list and detail caches."""
    mock_result = Mock()
    mock_result.rowcount = 1
    mock_db.execute.return_value = mock_result

    response = client.put(
        "/api/v1/coupon/123",
        data=json.dumps({"value": 25}),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert mock_cache.keys.call_count >= 1
    cache_patterns = [str(call) for call in mock_cache.keys.call_args_list]
    assert any("coupons:list:" in p for p in cache_patterns)
    assert any("coupons:id:123" in p for p in cache_patterns)


def test_delete_coupon_invalidates_cache(client, mock_db, mock_cache):
    """Deleting a coupon should invalidate list and detail caches."""
    mock_result = Mock()
    mock_result.rowcount = 1
    mock_db.execute.return_value = mock_result

    response = client.delete("/api/v1/coupon/123")

    assert response.status_code == 200
    assert mock_cache.keys.call_count >= 1
    cache_patterns = [str(call) for call in mock_cache.keys.call_args_list]
    assert any("coupons:list:" in p for p in cache_patterns)
    assert any("coupons:id:123" in p for p in cache_patterns)


def test_get_coupon_caches_response(client, mock_db, mock_cache):
    """GET requests should populate cache."""
    mock_row = Mock()
    mock_row._mapping = {
        "id": 123,
        "code": "SAVE20",
        "name": "20% Off",
        "value": 20,
        "active": True,
    }
    mock_result = Mock()
    mock_result.fetchone.return_value = mock_row
    mock_db.execute.return_value = mock_result

    response = client.get("/api/v1/coupon/123")

    assert response.status_code == 200
    assert mock_cache.get.called
    assert mock_cache.setex.called
