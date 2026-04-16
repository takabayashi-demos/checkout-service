"""Checkout service - cart and order processing."""
from flask import Flask, request, jsonify
import uuid
from datetime import datetime

app = Flask(__name__)

_coupons = {}


@app.route("/health")
def health():
    return jsonify({"status": "UP", "service": "checkout-service"})


@app.route("/api/v1/coupon", methods=["GET"])
def list_coupons():
    limit = request.args.get("limit", 20, type=int)
    limit = max(1, min(limit, 100))
    items = list(_coupons.values())[:limit]
    return jsonify({"items": items, "total": len(_coupons)})


@app.route("/api/v1/coupon/<coupon_id>", methods=["GET"])
def get_coupon(coupon_id):
    coupon = _coupons.get(coupon_id)
    if not coupon:
        return jsonify({"error": "Coupon not found"}), 404
    return jsonify(coupon)


@app.route("/api/v1/coupon", methods=["POST"])
def create_coupon():
    data = request.get_json(silent=True)
    if not data or "name" not in data or "value" not in data:
        return jsonify({"error": "name and value are required"}), 400

    if not isinstance(data["value"], (int, float)) or data["value"] <= 0:
        return jsonify({"error": "value must be a positive number"}), 400

    coupon_id = str(uuid.uuid4())[:8]
    coupon = {
        "id": coupon_id,
        "name": data["name"],
        "value": data["value"],
        "created_at": datetime.utcnow().isoformat(),
    }
    _coupons[coupon_id] = coupon
    return jsonify(coupon), 201


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
