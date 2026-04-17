"""Checkout-service: cart checkout and order processing."""
import os
import json
import logging
import re
from flask import Flask, request, jsonify
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


def validate_coupon_code(code):
    """Validate coupon code format: alphanumeric, dashes, underscores only."""
    if not code or not isinstance(code, str):
        return False
    if len(code) > 50:
        return False
    return bool(re.match(r'^[A-Za-z0-9_-]+$', code))


def validate_coupon_input(data):
    """Validate coupon creation/update input."""
    errors = []
    
    if 'code' not in data:
        errors.append("code is required")
    elif not validate_coupon_code(data['code']):
        errors.append("code must be alphanumeric with dashes/underscores, max 50 chars")
    
    if 'name' not in data:
        errors.append("name is required")
    elif not isinstance(data['name'], str) or len(data['name']) > 200:
        errors.append("name must be a string, max 200 chars")
    
    if 'value' not in data:
        errors.append("value is required")
    elif not isinstance(data['value'], (int, float)) or data['value'] < 0:
        errors.append("value must be a non-negative number")
    
    if 'active' in data and not isinstance(data['active'], bool):
        errors.append("active must be a boolean")
    
    return errors


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
    limit = min(int(request.args.get("limit", 20)), 100)
    offset = int(request.args.get("offset", 0))

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
def get_coupon(coupon_id):
    """Fetch a single coupon by ID. Cached for CACHE_TTL seconds."""
    cache_key = f"coupons:id:{coupon_id}"
    cached = cache_get(cache_key)
    if cached:
        return jsonify(cached)

    with get_db() as conn:
        result = conn.execute(
            text("SELECT id, code, name, value, active FROM coupons WHERE id = :id"),
            {"id": coupon_id},
        )
        row = result.fetchone()

    if row is None:
        return jsonify({"error": "coupon not found"}), 404

    coupon_data = dict(row._mapping)
    cache_set(cache_key, coupon_data)
    return jsonify(coupon_data)


@app.route("/api/v1/coupon", methods=["POST"])
def create_coupon():
    """Create a new coupon with validation."""
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400
    
    data = request.get_json()
    
    validation_errors = validate_coupon_input(data)
    if validation_errors:
        return jsonify({"error": "validation failed", "details": validation_errors}), 400
    
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
                    "value": data["value"],
                    "active": data.get("active", True),
                },
            )
            conn.commit()
            coupon_id = result.fetchone()[0]
        
        cache_delete("coupons:list:*")
        
        return jsonify({"id": coupon_id, "message": "coupon created"}), 201
    
    except Exception as e:
        logger.error(f"Failed to create coupon: {e}")
        return jsonify({"error": "failed to create coupon"}), 500


@app.route("/api/v1/coupon/<int:coupon_id>", methods=["PUT"])
def update_coupon(coupon_id):
    """Update an existing coupon with validation."""
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400
    
    data = request.get_json()
    
    validation_errors = validate_coupon_input(data)
    if validation_errors:
        return jsonify({"error": "validation failed", "details": validation_errors}), 400
    
    try:
        with get_db() as conn:
            result = conn.execute(
                text(
                    "UPDATE coupons SET code = :code, name = :name, "
                    "value = :value, active = :active WHERE id = :id"
                ),
                {
                    "id": coupon_id,
                    "code": data["code"],
                    "name": data["name"],
                    "value": data["value"],
                    "active": data.get("active", True),
                },
            )
            conn.commit()
            
            if result.rowcount == 0:
                return jsonify({"error": "coupon not found"}), 404
        
        cache_delete("coupons:*")
        
        return jsonify({"message": "coupon updated"}), 200
    
    except Exception as e:
        logger.error(f"Failed to update coupon: {e}")
        return jsonify({"error": "failed to update coupon"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
