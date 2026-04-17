# Checkout Service

Cart checkout and order processing microservice.

**Team:** Cart & Checkout  
**Stack:** Python 3.11, Flask, PostgreSQL, Redis

## Architecture

This service handles checkout flows and coupon management. Key design decisions:

- **Connection pooling** (SQLAlchemy QueuePool): Reuses DB connections across requests. Pool size 10, max overflow 20. Eliminates per-request connection overhead.
- **Redis caching** (60s TTL): Coupon reads are cached during checkout surges. Cache invalidation on writes keeps data consistent.
- **Graceful degradation**: Service continues without Redis if cache is unavailable.

## API Endpoints

### Health Check
```
GET /health
```
Returns service and cache status.

**Response:**
```json
{
  "status": "UP",
  "service": "checkout-service",
  "cache": "UP"
}
```

### List Coupons
```
GET /api/v1/coupon?limit=20&offset=0
```
Returns paginated coupon list. Cached for 60s.

**Query Parameters:**
- `limit` (optional): Max results, 1-100, default 20
- `offset` (optional): Pagination offset, default 0

**Response:**
```json
{
  "items": [
    {
      "id": 1,
      "code": "SAVE20",
      "name": "20% Off",
      "value": 20,
      "active": true
    }
  ],
  "limit": 20,
  "offset": 0
}
```

### Get Coupon
```
GET /api/v1/coupon/<coupon_id>
```
Fetch single coupon by ID. Cached for 60s.

**Response:**
```json
{
  "id": 1,
  "code": "SAVE20",
  "name": "20% Off",
  "value": 20,
  "active": true
}
```

**Errors:**
- `404` if coupon not found

### Create Coupon
```
POST /api/v1/coupon
```
Create new coupon. Invalidates list cache.

**Request Body:**
```json
{
  "code": "SAVE20",
  "name": "20% Off",
  "value": 20,
  "active": true
}
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://checkout:checkout@localhost:5432/checkout_db` | PostgreSQL connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection string |
| `COUPON_CACHE_TTL` | `60` | Cache TTL in seconds |
| `PORT` | `5000` | Service port |

## Local Development

### Prerequisites
- Python 3.11+
- PostgreSQL 14+
- Redis 7+

### Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Start PostgreSQL and Redis:
```bash
docker-compose up -d postgres redis
```

3. Run migrations:
```bash
python migrate.py
```

4. Start the service:
```bash
python app.py
```

Service runs on `http://localhost:5000`.

### Running Tests
```bash
pytest test_app.py -v
```

## Deployment

### Kubernetes

Service expects:
- PostgreSQL accessible via `DATABASE_URL`
- Redis accessible via `REDIS_URL`
- Health check endpoint: `/health`
- Readiness probe: same as liveness

### Performance Notes

- Connection pool tuned for 10-30 concurrent connections
- Cache hit rate should be >80% during normal traffic
- If Redis is down, service degrades gracefully (cache misses go to DB)

## Monitoring

**Key Metrics:**
- Cache hit rate (target >80%)
- DB connection pool utilization (alert if >80%)
- P95 response time for `/api/v1/coupon/<id>` (target <50ms)

**Logs:**
- All requests logged at INFO level
- Cache failures logged at WARNING (non-fatal)
