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
    """Create a new coupon."""
    data = request.get_json()
    required = ["code", "name", "value"]
    if not all(field in data for field in required):
        return jsonify({"error": "missing required fields"}), 400

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

    cache_delete("coupons:*")
    return jsonify({"id": coupon_id}), 201


@app.route("/api/v1/coupon/validate", methods=["POST"])
def validate_coupon():
    """Validate a coupon code against a cart total."""
    data = request.get_json()
    if not data or "code" not in data or "cart_total" not in data:
        return jsonify({"error": "missing code or cart_total"}), 400

    code = data["code"].upper()
    cart_total = float(data["cart_total"])

    cache_key = f"coupons:validate:{code}"
    cached = cache_get(cache_key)

    if cached is None:
        with get_db() as conn:
            result = conn.execute(
                text("SELECT id, code, name, value, active FROM coupons WHERE UPPER(code) = :code"),
                {"code": code},
            )
            row = result.fetchone()

        if row is None:
            return jsonify({"valid": False, "message": "coupon not found"}), 200

        coupon = dict(row._mapping)
        cache_set(cache_key, coupon)
    else:
        coupon = cached

    if not coupon.get("active", False):
        return jsonify({"valid": False, "message": "coupon is inactive"}), 200

    discount = float(coupon["value"])
    final_total = max(0, cart_total - discount)

    return jsonify({
        "valid": True,
        "coupon_code": coupon["code"],
        "discount_amount": discount,
        "cart_total": cart_total,
        "final_total": final_total,
        "message": "coupon applied successfully"
    }), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
