"""Checkout-service: cart checkout and order processing."""
import os
import json
import logging
from flask import Flask, request, jsonify
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool
import redis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Database and cache configuration
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://checkout:checkout@localhost:5432/checkout_db"
)
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CACHE_TTL = int(os.environ.get("COUPON_CACHE_TTL", 60))

# Cache key prefixes
CACHE_PREFIX_COUPON_LIST = "coupons:list"
CACHE_PREFIX_COUPON_ID = "coupons:id"

# Connection pooling — reuse connections across requests instead of
# opening a new connection per request (was the main latency source).
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_recycle=300,
    pool_pre_ping=True,
)

# Redis cache — coupon reads are extremely hot during checkout surges.
# A 60s TTL is safe because coupons change infrequently and we
# invalidate on write.
try:
    cache = redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=0.5)
    cache.ping()
    logger.info("Redis cache connected")
except redis.ConnectionError:
    logger.warning("Redis unavailable, running without cache")
    cache = None


def build_cache_key(prefix, *parts):
    """Build a cache key from prefix and parts."""
    return ":".join([prefix] + [str(p) for p in parts])


def cache_get(key):
    """Read from cache, return None on miss or if cache is unavailable."""
    if cache is None:
        return None
    try:
        raw = cache.get(key)
        return json.loads(raw) if raw else None
    except (redis.RedisError, json.JSONDecodeError):
        return None


def cache_set(key, value, ttl=CACHE_TTL):
    """Write to cache. Failures are silently ignored."""
    if cache is None:
        return
    try:
        cache.setex(key, ttl, json.dumps(value))
    except redis.RedisError:
        pass


def cache_delete(pattern):
    """Invalidate cache entries matching a prefix."""
    if cache is None:
        return
    try:
        keys = cache.keys(pattern)
        if keys:
            cache.delete(*keys)
    except redis.RedisError:
        pass


def get_db():
    """Return a connection from the pool."""
    return engine.connect()


def error_response(message, status_code=400):
    """Create a standardized error response."""
    logger.warning(f"Error response: {message} (status={status_code})")
    return jsonify({"error": message}), status_code


@app.route("/health")
def health():
    """Liveness probe."""
    cache_status = "UP" if cache else "DEGRADED"
    return jsonify(
        {"status": "UP", "service": "checkout-service", "cache": cache_status}
    )


@app.route("/api/v1/coupon", methods=["GET"])
def list_coupons():
    """List coupons with pagination. Uses server-side cursor for large sets."""
    try:
        limit = min(int(request.args.get("limit", 20)), 100)
        offset = int(request.args.get("offset", 0))
    except ValueError:
        return error_response("Invalid limit or offset parameter")

    cache_key = build_cache_key(CACHE_PREFIX_COUPON_LIST, limit, offset)
    cached = cache_get(cache_key)
    if cached:
        return jsonify(cached)

    try:
        with get_db() as conn:
            result = conn.execute(
                text(
                    "SELECT id, code, name, value, active "
                    "FROM coupons ORDER BY id LIMIT :limit OFFSET :offset"
                ),
                {"limit": limit, "offset": offset},
            )
            items = [dict(row._mapping) for row in result]
    except Exception as e:
        logger.error(f"Database error in list_coupons: {e}")
        return error_response("Database error", status_code=500)

    response_data = {"items": items, "limit": limit, "offset": offset}
    cache_set(cache_key, response_data)
    return jsonify(response_data)


@app.route("/api/v1/coupon/<coupon_id>", methods=["GET"])
def get_coupon(coupon_id):
    """Fetch a single coupon by ID. Cached for CACHE_TTL seconds."""
    try:
        coupon_id = int(coupon_id)
    except ValueError:
        return error_response("Invalid coupon ID")

    cache_key = build_cache_key(CACHE_PREFIX_COUPON_ID, coupon_id)
    cached = cache_get(cache_key)
    if cached:
        return jsonify(cached)

    try:
        with get_db() as conn:
            result = conn.execute(
                text("SELECT id, code, name, value, active FROM coupons WHERE id = :id"),
                {"id": coupon_id},
            )
            row = result.fetchone()
    except Exception as e:
        logger.error(f"Database error in get_coupon: {e}")
        return error_response("Database error", status_code=500)

    if row is None:
        return error_response("Coupon not found", status_code=404)

    coupon_data = dict(row._mapping)
    cache_set(cache_key, coupon_data)
    return jsonify(coupon_data)


@app.route("/api/v1/coupon", methods=["POST"])
def create_coupon():
    """Create a new coupon."""
    data = request.get_json()
    if not data:
        return error_response("Request body must be JSON")

    required_fields = ["code", "name", "value"]
    missing = [f for f in required_fields if f not in data]
    if missing:
        return error_response(f"Missing required fields: {', '.join(missing)}")

    try:
        with get_db() as conn:
            result = conn.execute(
                text(
                    "INSERT INTO coupons (code, name, value, active) "
                    "VALUES (:code, :name, :value, :active) RETURNING id"
                ),
                {
                    "code": data["code"],
                    "name": data["name"],
                    "value": float(data["value"]),
                    "active": data.get("active", True),
                },
            )
            conn.commit()
            coupon_id = result.fetchone()[0]
    except ValueError:
        return error_response("Invalid value format")
    except Exception as e:
        logger.error(f"Database error in create_coupon: {e}")
        return error_response("Database error", status_code=500)

    cache_delete(f"{CACHE_PREFIX_COUPON_LIST}:*")
    logger.info(f"Created coupon {coupon_id}")
    return jsonify({"id": coupon_id}), 201


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
