"""Tests for checkout-service."""
import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from app import app, cache_get, cache_set


@pytest.fixture
def client():
    """Flask test client."""
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def mock_db():
    """Mock database connection."""
    with patch("app.get_db") as mock:
        yield mock


@pytest.fixture
def mock_cache():
    """Mock Redis cache."""
    with patch("app.cache") as mock:
        mock.get.return_value = None
        yield mock


def test_validate_coupon_valid(client, mock_db, mock_cache):
    """Valid active coupon returns valid=true with coupon details."""
    mock_conn = MagicMock()
    mock_db.return_value.__enter__.return_value = mock_conn
    
    mock_row = Mock()
    mock_row._mapping = {
        "id": 1,
        "code": "SAVE20",
        "name": "20% Off",
        "value": 20,
        "active": True,
    }
    mock_conn.execute.return_value.fetchone.return_value = mock_row

    response = client.post(
        "/api/v1/coupon/validate",
        data=json.dumps({"code": "SAVE20"}),
        content_type="application/json",
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["valid"] is True
    assert data["coupon"]["code"] == "SAVE20"
    assert data["coupon"]["value"] == 20
    assert data["error"] is None


def test_validate_coupon_inactive(client, mock_db, mock_cache):
    """Inactive coupon returns valid=false with error message."""
    mock_conn = MagicMock()
    mock_db.return_value.__enter__.return_value = mock_conn
    
    mock_row = Mock()
    mock_row._mapping = {
        "id": 2,
        "code": "EXPIRED",
        "name": "Expired Coupon",
        "value": 10,
        "active": False,
    }
    mock_conn.execute.return_value.fetchone.return_value = mock_row

    response = client.post(
        "/api/v1/coupon/validate",
        data=json.dumps({"code": "EXPIRED"}),
        content_type="application/json",
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["valid"] is False
    assert data["coupon"] is None
    assert data["error"] == "coupon is inactive"


def test_validate_coupon_not_found(client, mock_db, mock_cache):
    """Non-existent coupon returns 404."""
    mock_conn = MagicMock()
    mock_db.return_value.__enter__.return_value = mock_conn
    mock_conn.execute.return_value.fetchone.return_value = None

    response = client.post(
        "/api/v1/coupon/validate",
        data=json.dumps({"code": "NOTFOUND"}),
        content_type="application/json",
    )

    assert response.status_code == 404
    data = response.get_json()
    assert data["valid"] is False
    assert data["error"] == "coupon not found"


def test_validate_coupon_missing_code(client):
    """Request without code returns 400."""
    response = client.post(
        "/api/v1/coupon/validate",
        data=json.dumps({}),
        content_type="application/json",
    )

    assert response.status_code == 400
    data = response.get_json()
    assert "error" in data
    assert "required" in data["error"]


def test_validate_coupon_cache_hit(client, mock_cache):
    """Cached validation result is returned without DB query."""
    cached_response = {
        "valid": True,
        "coupon": {"id": 1, "code": "CACHED", "value": 15, "active": True},
        "error": None,
    }
    mock_cache.get.return_value = json.dumps(cached_response)

    with patch("app.get_db") as mock_db:
        response = client.post(
            "/api/v1/coupon/validate",
            data=json.dumps({"code": "CACHED"}),
            content_type="application/json",
        )

        mock_db.assert_not_called()

    assert response.status_code == 200
    data = response.get_json()
    assert data["valid"] is True
    assert data["coupon"]["code"] == "CACHED"
