"""Checkout-service: cart checkout and order processing."""
from flask import Flask, jsonify, request

app = Flask(__name__)

# In-memory store (replaced by DynamoDB in prod)
_coupons = {}
_counter = 0


@app.route("/health")
def health():
    return jsonify({"status": "UP", "service": "checkout-service"})


@app.route("/api/v1/coupon", methods=["POST"])
def create_coupon():
    global _counter
    data = request.get_json(silent=True) or {}

    name = data.get("name")
    value = data.get("value")

    if not name or value is None:
        return jsonify({"error": "name and value are required"}), 400

    if not isinstance(value, (int, float)) or value <= 0:
        return jsonify({"error": "value must be a positive number"}), 400

    _counter += 1
    coupon_id = f"cpn-{_counter}"
    _coupons[coupon_id] = {"id": coupon_id, "name": name, "value": value}

    return jsonify(_coupons[coupon_id]), 201


@app.route("/api/v1/coupon/<coupon_id>", methods=["GET"])
def get_coupon(coupon_id):
    coupon = _coupons.get(coupon_id)
    if not coupon:
        return jsonify({"error": "coupon not found"}), 404
    return jsonify(coupon)


@app.route("/api/v1/coupon", methods=["GET"])
def list_coupons():
    limit = request.args.get("limit", 20, type=int)
    items = list(_coupons.values())[:limit]
    return jsonify({"items": items, "total": len(_coupons)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
