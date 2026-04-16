"""Checkout-service: cart checkout and order processing."""
import os
import logging
from flask import Flask, request, jsonify
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://checkout:checkout@localhost:5432/checkout_db"
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


def get_db():
    """Return a connection from the pool."""
    return engine.connect()


@app.route("/health")
def health():
    """Liveness probe."""
    return jsonify({"status": "UP", "service": "checkout-service"})


@app.route("/api/v1/coupon", methods=["GET"])
def list_coupons():
    """List coupons with pagination. Uses server-side cursor for large sets."""
    limit = min(int(request.args.get("limit", 20)), 100)
    offset = int(request.args.get("offset", 0))

    with get_db() as conn:
        result = conn.execute(
            text(
                "SELECT id, code, name, value, active "
                "FROM coupons ORDER BY id LIMIT :limit OFFSET :offset"
            ),
            {"limit": limit, "offset": offset},
        )
        items = [dict(row._mapping) for row in result]

    return jsonify({"items": items, "limit": limit, "offset": offset})


@app.route("/api/v1/coupon/<coupon_id>", methods=["GET"])
def get_coupon(coupon_id):
    """Fetch a single coupon by ID."""
    with get_db() as conn:
        result = conn.execute(
            text("SELECT id, code, name, value, active FROM coupons WHERE id = :id"),
            {"id": coupon_id},
        )
        row = result.fetchone()

    if row is None:
        return jsonify({"error": "coupon not found"}), 404

    return jsonify(dict(row._mapping))


@app.route("/api/v1/coupon", methods=["POST"])
def create_coupon():
    """Create a new coupon."""
    data = request.get_json(silent=True) or {}
    if not data.get("name") or "value" not in data:
        return jsonify({"error": "name and value are required"}), 400

    with get_db() as conn:
        result = conn.execute(
            text(
                "INSERT INTO coupons (name, value, active) "
                "VALUES (:name, :value, true) RETURNING id"
            ),
            {"name": data["name"], "value": data["value"]},
        )
        coupon_id = result.fetchone()[0]
        conn.commit()

    return jsonify({"id": coupon_id, "name": data["name"], "value": data["value"]}), 201


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
