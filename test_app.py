"""Unit tests for checkout-service."""
import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from app import app, cache_get, cache_set, cache_delete


@pytest.fixture
def client():
    """Test client fixture."""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def mock_db():
    """Mock database connection."""
    with patch('app.get_db') as mock:
        yield mock


@pytest.fixture
def mock_cache():
    """Mock Redis cache."""
    with patch('app.cache') as mock:
        yield mock


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_health_check_with_cache(self, client, mock_cache):
        """Health endpoint returns UP when cache is available."""
        mock_cache.__bool__.return_value = True
        response = client.get('/health')
        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'UP'
        assert data['service'] == 'checkout-service'
        assert data['cache'] == 'UP'

    def test_health_check_without_cache(self, client):
        """Health endpoint returns DEGRADED when cache is unavailable."""
        with patch('app.cache', None):
            response = client.get('/health')
            assert response.status_code == 200
            data = response.get_json()
            assert data['status'] == 'UP'
            assert data['cache'] == 'DEGRADED'


class TestListCoupons:
    """Tests for GET /api/v1/coupon endpoint."""

    def test_list_coupons_default_pagination(self, client, mock_db, mock_cache):
        """List coupons with default limit and offset."""
        mock_cache.get.return_value = None
        mock_conn = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_conn

        mock_result = [
            {'id': 1, 'code': 'SAVE10', 'name': 'Save 10%', 'value': 10, 'active': True},
            {'id': 2, 'code': 'SAVE20', 'name': 'Save 20%', 'value': 20, 'active': True}
        ]
        mock_conn.execute.return_value = [Mock(_mapping=r) for r in mock_result]

        response = client.get('/api/v1/coupon')
        assert response.status_code == 200
        data = response.get_json()
        assert data['limit'] == 20
        assert data['offset'] == 0
        assert len(data['items']) == 2
        assert data['items'][0]['code'] == 'SAVE10'

    def test_list_coupons_custom_pagination(self, client, mock_db, mock_cache):
        """List coupons with custom limit and offset."""
        mock_cache.get.return_value = None
        mock_conn = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.return_value = []

        response = client.get('/api/v1/coupon?limit=50&offset=10')
        assert response.status_code == 200
        data = response.get_json()
        assert data['limit'] == 50
        assert data['offset'] == 10

    def test_list_coupons_limit_cap(self, client, mock_db, mock_cache):
        """List coupons enforces max limit of 100."""
        mock_cache.get.return_value = None
        mock_conn = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.return_value = []

        response = client.get('/api/v1/coupon?limit=200')
        assert response.status_code == 200
        data = response.get_json()
        assert data['limit'] == 100

    def test_list_coupons_cache_hit(self, client, mock_cache):
        """List coupons returns cached data when available."""
        cached_data = {'items': [{'id': 1, 'code': 'CACHED'}], 'limit': 20, 'offset': 0}
        mock_cache.get.return_value = json.dumps(cached_data)

        response = client.get('/api/v1/coupon')
        assert response.status_code == 200
        data = response.get_json()
        assert data == cached_data
        assert data['items'][0]['code'] == 'CACHED'

    def test_list_coupons_zero_limit(self, client, mock_db, mock_cache):
        """List coupons handles zero limit edge case."""
        mock_cache.get.return_value = None
        mock_conn = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.return_value = []

        response = client.get('/api/v1/coupon?limit=0')
        assert response.status_code == 200
        data = response.get_json()
        assert data['limit'] == 0


class TestGetCoupon:
    """Tests for GET /api/v1/coupon/<id> endpoint."""

    def test_get_coupon_success(self, client, mock_db, mock_cache):
        """Get coupon by ID returns coupon data."""
        mock_cache.get.return_value = None
        mock_conn = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_conn

        mock_row = Mock(_mapping={
            'id': 1,
            'code': 'SAVE10',
            'name': 'Save 10%',
            'value': 10,
            'active': True
        })
        mock_conn.execute.return_value.fetchone.return_value = mock_row

        response = client.get('/api/v1/coupon/1')
        assert response.status_code == 200
        data = response.get_json()
        assert data['id'] == 1
        assert data['code'] == 'SAVE10'
        assert data['value'] == 10

    def test_get_coupon_not_found(self, client, mock_db, mock_cache):
        """Get coupon returns 404 when coupon doesn't exist."""
        mock_cache.get.return_value = None
        mock_conn = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchone.return_value = None

        response = client.get('/api/v1/coupon/999')
        assert response.status_code == 404
        data = response.get_json()
        assert 'error' in data
        assert data['error'] == 'coupon not found'

    def test_get_coupon_cache_hit(self, client, mock_cache):
        """Get coupon returns cached data when available."""
        cached_coupon = {
            'id': 1,
            'code': 'SAVE10',
            'name': 'Save 10%',
            'value': 10,
            'active': True
        }
        mock_cache.get.return_value = json.dumps(cached_coupon)

        response = client.get('/api/v1/coupon/1')
        assert response.status_code == 200
        data = response.get_json()
        assert data == cached_coupon

    def test_get_coupon_invalid_id_type(self, client, mock_db, mock_cache):
        """Get coupon handles non-numeric IDs gracefully."""
        mock_cache.get.return_value = None
        mock_conn = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchone.return_value = None

        response = client.get('/api/v1/coupon/invalid')
        assert response.status_code == 404


class TestCacheHelpers:
    """Tests for cache utility functions."""

    def test_cache_get_miss(self):
        """cache_get returns None on cache miss."""
        with patch('app.cache') as mock_cache:
            mock_cache.get.return_value = None
            result = cache_get('test_key')
            assert result is None

    def test_cache_get_hit(self):
        """cache_get returns parsed JSON on cache hit."""
        with patch('app.cache') as mock_cache:
            mock_cache.get.return_value = '{"foo": "bar"}'
            result = cache_get('test_key')
            assert result == {"foo": "bar"}

    def test_cache_get_no_cache(self):
        """cache_get returns None when cache is unavailable."""
        with patch('app.cache', None):
            result = cache_get('test_key')
            assert result is None

    def test_cache_get_redis_error(self):
        """cache_get returns None on Redis error."""
        with patch('app.cache') as mock_cache:
            mock_cache.get.side_effect = Exception("Redis connection error")
            result = cache_get('test_key')
            assert result is None

    def test_cache_get_invalid_json(self):
        """cache_get returns None on invalid JSON."""
        with patch('app.cache') as mock_cache:
            mock_cache.get.return_value = 'not valid json{'
            result = cache_get('test_key')
            assert result is None

    def test_cache_set_success(self):
        """cache_set writes to cache with TTL."""
        with patch('app.cache') as mock_cache:
            cache_set('test_key', {'foo': 'bar'}, ttl=120)
            mock_cache.setex.assert_called_once_with('test_key', 120, '{"foo": "bar"}')

    def test_cache_set_default_ttl(self):
        """cache_set uses default TTL when not specified."""
        with patch('app.cache') as mock_cache:
            with patch('app.CACHE_TTL', 60):
                cache_set('test_key', {'foo': 'bar'})
                mock_cache.setex.assert_called_once_with('test_key', 60, '{"foo": "bar"}')

    def test_cache_set_no_cache(self):
        """cache_set is a no-op when cache is unavailable."""
        with patch('app.cache', None):
            cache_set('test_key', {'foo': 'bar'})

    def test_cache_set_redis_error(self):
        """cache_set silently handles Redis errors."""
        with patch('app.cache') as mock_cache:
            mock_cache.setex.side_effect = Exception("Redis write error")
            cache_set('test_key', {'foo': 'bar'})

    def test_cache_delete_success(self):
        """cache_delete removes matching keys."""
        with patch('app.cache') as mock_cache:
            mock_cache.keys.return_value = ['key1', 'key2', 'key3']
            cache_delete('key*')
            mock_cache.delete.assert_called_once_with('key1', 'key2', 'key3')

    def test_cache_delete_no_keys(self):
        """cache_delete handles no matching keys."""
        with patch('app.cache') as mock_cache:
            mock_cache.keys.return_value = []
            cache_delete('nonexistent*')
            mock_cache.delete.assert_not_called()

    def test_cache_delete_no_cache(self):
        """cache_delete is a no-op when cache is unavailable."""
        with patch('app.cache', None):
            cache_delete('key*')

    def test_cache_delete_redis_error(self):
        """cache_delete silently handles Redis errors."""
        with patch('app.cache') as mock_cache:
            mock_cache.keys.side_effect = Exception("Redis error")
            cache_delete('key*')
