"""Checkout-service: cart checkout and order processing."""
import os
import json
import logging
import re
from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool
import redis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://checkout:checkout@localhost:5432/checkout_db"
)
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CACHE_TTL = int(os.environ.get("COUPON_CACHE_TTL", 60))

# Rate limiting to prevent abuse
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["100 per hour"],
    storage_uri=REDIS_URL if REDIS_URL else "memory://",
)

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


def validate_integer(value, name, min_val=0, max_val=10000):
    """Validate and sanitize integer input."""
    try:
        int_val = int(value)
        if int_val < min_val or int_val > max_val:
            raise ValueError(f"{name} must be between {min_val} and {max_val}")
        return int_val
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid {name}: {str(e)}")


def validate_coupon_code(code):
    """Validate coupon code format to prevent injection."""
    if not isinstance(code, str):
        raise ValueError("Coupon code must be a string")
    if len(code) < 3 or len(code) > 50:
        raise ValueError("Coupon code must be 3-50 characters")
    if not re.match(r"^[A-Z0-9_-]+$", code):
        raise ValueError("Coupon code contains invalid characters")
    return code


def validate_coupon_data(data):
    """Validate coupon creation payload."""
    required_fields = ["code", "name", "value"]
    for field in required_fields:
        if field not in data:
            raise ValueError(f"Missing required field: {field}")
    
    validated = {
        "code": validate_coupon_code(data["code"]),
        "name": str(data["name"])[:200],
        "value": validate_integer(data["value"], "value", min_val=1, max_val=1000000),
        "active": bool(data.get("active", True)),
    }
    return validated


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


@app.route("/health")
@limiter.exempt
def health():
    """Liveness probe."""
    cache_status = "UP" if cache else "DEGRADED"
    return jsonify(
        {"status": "UP", "service": "checkout-service", "cache": cache_status}
    )


@app.route("/api/v1/coupon", methods=["GET"])
@limiter.limit("200 per hour")
def list_coupons():
    """List coupons with pagination. Uses server-side cursor for large sets."""
    try:
        limit = validate_integer(request.args.get("limit", 20), "limit", min_val=1, max_val=100)
        offset = validate_integer(request.args.get("offset", 0), "offset", min_val=0, max_val=1000000)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    cache_key = f"coupons:list:{limit}:{offset}"
    cached = cache_get(cache_key)
    if cached:
        return jsonify(cached)

    with get_db() as conn:
        result = conn.execute(
            text(
                "SELECT id, code, name, value, active "
                "FROM coupons ORDER BY id LIMIT :limit OFFSET :offset"
            ),
            {"limit": limit, "offset": offset},
        )
        items = [dict(row._mapping) for row in result]

    response_data = {"items": items, "limit": limit, "offset": offset}
    cache_set(cache_key, response_data)
    return jsonify(response_data)


@app.route("/api/v1/coupon/<coupon_id>", methods=["GET"])
@limiter.limit("300 per hour")
def get_coupon(coupon_id):
    """Fetch a single coupon by ID. Cached for CACHE_TTL seconds."""
    try:
        validated_id = validate_integer(coupon_id, "coupon_id", min_val=1, max_val=2147483647)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    cache_key = f"coupons:id:{validated_id}"
    cached = cache_get(cache_key)
    if cached:
        return jsonify(cached)

    with get_db() as conn:
        result = conn.execute(
            text("SELECT id, code, name, value, active FROM coupons WHERE id = :id"),
            {"id": validated_id},
        )
        row = result.fetchone()

    if row is None:
        return jsonify({"error": "coupon not found"}), 404

    coupon_data = dict(row._mapping)
    cache_set(cache_key, coupon_data)
    return jsonify(coupon_data)


@app.route("/api/v1/coupon", methods=["POST"])
@limiter.limit("20 per hour")
def create_coupon():
    """Create a new coupon."""
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400

    try:
        validated_data = validate_coupon_data(request.json)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    with get_db() as conn:
        result = conn.execute(
            text(
                "INSERT INTO coupons (code, name, value, active) "
                "VALUES (:code, :name, :value, :active) RETURNING id"
            ),
            validated_data,
        )
        conn.commit()
        new_id = result.fetchone()[0]

    cache_delete("coupons:*")
    return jsonify({"id": new_id, **validated_data}), 201


@app.route("/api/v1/coupon/<coupon_id>", methods=["DELETE"])
@limiter.limit("20 per hour")
def delete_coupon(coupon_id):
    """Delete a coupon."""
    try:
        validated_id = validate_integer(coupon_id, "coupon_id", min_val=1, max_val=2147483647)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    with get_db() as conn:
        result = conn.execute(
            text("DELETE FROM coupons WHERE id = :id"),
            {"id": validated_id},
        )
        conn.commit()

    cache_delete("coupons:*")
    return jsonify({"deleted": validated_id}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
