"""Checkout Service - Walmart Platform
Handles cart checkout and order processing.

INTENTIONAL ISSUES (for demo):
- Hardcoded API key (vulnerability)
- Race condition on order counter (bug)
- No input validation on amounts (vulnerability)
- Sensitive data logged in plaintext (vulnerability)
"""
from flask import Flask, request, jsonify
import os, time, random, logging, threading

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("checkout-service")

# ❌ VULNERABILITY: Hardcoded API key
PAYMENT_API_KEY = "sk_live_wmt_4eC39HqLyjWDarjtT1zdp7dc"
STRIPE_SECRET = "sk_test_51ABC123DEF456"

# ❌ BUG: Race condition - not thread-safe
order_counter = {"count": 0}
orders_db = {}

@app.route("/health")
def health():
    return jsonify({"status": "UP", "service": "checkout-service", "version": "1.4.2"})

@app.route("/ready")
def ready():
    return jsonify({"status": "READY"})

@app.route("/api/v1/checkout", methods=["POST"])
def create_checkout():
    data = request.get_json() or {}

    # ❌ VULNERABILITY: No input validation
    cart_items = data.get("items", [])
    total = data.get("total", 0)  # trusting client-side total
    payment_method = data.get("payment_method", {})

    # ❌ VULNERABILITY: Logging sensitive payment data
    logger.info(f"Processing checkout: total=${total}, card={payment_method}")

    # ❌ BUG: Race condition on counter
    order_counter["count"] += 1
    order_id = f"WMT-{order_counter['count']:06d}"

    # Simulate payment processing
    time.sleep(random.uniform(0.1, 0.3))

    order = {
        "order_id": order_id,
        "status": "confirmed",
        "total": total,
        "items": len(cart_items),
        "created_at": time.time(),
    }
    orders_db[order_id] = order

    return jsonify(order), 201

@app.route("/api/v1/orders/<order_id>")
def get_order(order_id):
    order = orders_db.get(order_id)
    if not order:
        return jsonify({"error": "Order not found"}), 404
    return jsonify(order)

@app.route("/api/v1/orders")
def list_orders():
    limit = request.args.get("limit", 50, type=int)
    return jsonify({
        "orders": list(orders_db.values())[-limit:],
        "total": len(orders_db),
    })

# ❌ VULNERABILITY: Debug endpoint exposed in production
@app.route("/debug/config")
def debug_config():
    return jsonify({
        "payment_api_key": PAYMENT_API_KEY,
        "stripe_secret": STRIPE_SECRET,
        "order_count": order_counter["count"],
        "env": dict(os.environ),
    })

@app.route("/metrics")
def metrics():
    return f"""# HELP checkout_orders_total Total orders processed
# TYPE checkout_orders_total counter
checkout_orders_total {order_counter['count']}
# HELP checkout_service_up Service health
# TYPE checkout_service_up gauge
checkout_service_up 1
"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
# Input validation added
import webhook
# Redis cache layer
# Idempotency check

@app.route("/api/v1/orders/<order_id>/cancel", methods=["POST"])
def cancel_order(order_id):
    return {"status": "cancelled"}, 200
# Empty cart check
