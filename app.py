from flask import Flask, request, redirect, session, jsonify, render_template
import requests
import os
import secrets
import hashlib
import hmac
import json
from dotenv import load_dotenv

# Carica variabili da .env
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "fallback_secret")

# ---------------- CONFIG ----------------

SHOP = os.getenv("SHOPIFY_STORE")
CLIENT_ID = os.getenv("SHOPIFY_API_KEY")
CLIENT_SECRET = os.getenv("SHOPIFY_API_SECRET")

SCOPES = os.getenv("SCOPES")
REDIRECT_URI = os.getenv("REDIRECT_URI")

API_VERSION = "2026-01"

# 👇 QUESTE MANCAVANO
TOKEN_FILE = "token.json"
OPENED_FILE = "opened_orders.json"

# ---------------- TOKEN HELPERS ----------------

def save_token(token):
    with open(TOKEN_FILE, "w") as f:
        json.dump({"access_token": token}, f)

def load_token():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            return json.load(f).get("access_token")
    return None

# ---------------- OPENED ORDERS HELPERS ----------------

def load_opened():
    if os.path.exists(OPENED_FILE):
        with open(OPENED_FILE) as f:
            return json.load(f)
    return []

def save_opened(data):
    with open(OPENED_FILE, "w") as f:
        json.dump(data, f)

# ---------------- HOME ----------------

@app.route("/")
def index():
    token = load_token()

    if not token:
        state = secrets.token_hex(16)
        session["oauth_state"] = state

        auth_url = (
            f"https://{SHOP}/admin/oauth/authorize"
            f"?client_id={CLIENT_ID}"
            f"&scope={SCOPES}"
            f"&redirect_uri={REDIRECT_URI}"
            f"&state={state}"
        )
        return redirect(auth_url)

    return render_template("dashboard.html")

# ---------------- CALLBACK ----------------

@app.route("/callback")
def callback():
    state = request.args.get("state")
    if state != session.get("oauth_state"):
        return "Invalid state", 400

    code = request.args.get("code")
    hmac_received = request.args.get("hmac")

    params = request.args.to_dict()
    params.pop("hmac", None)

    sorted_params = "&".join(
        f"{k}={v}" for k, v in sorted(params.items())
    )

    calculated_hmac = hmac.new(
        CLIENT_SECRET.encode(),
        sorted_params.encode(),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(calculated_hmac, hmac_received):
        return "HMAC verification failed", 400

    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
    }

    response = requests.post(
        f"https://{SHOP}/admin/oauth/access_token",
        json=data
    )

    access_token = response.json().get("access_token")

    if not access_token:
        return "Token exchange failed", 400

    save_token(access_token)

    return redirect("/")

# ---------------- API ORDERS ----------------

@app.route("/api/orders")
def get_orders():
    token = load_token()

    if not token:
        return jsonify({"error": "Not authenticated"}), 401

    headers = {
        "X-Shopify-Access-Token": token
    }

    # Prendiamo gli ordini
    response = requests.get(
        f"https://{SHOP}/admin/api/{API_VERSION}/orders.json?status=any",
        headers=headers
    )

    orders = response.json().get("orders", [])
    opened_orders = load_opened()

    for order in orders:

        # stato aperto
        order["is_opened"] = order["id"] in opened_orders

        # cliente info
        customer = order.get("customer")
        if customer:
            order["customer_name"] = f"{customer.get('first_name','')} {customer.get('last_name','')}"
            order["customer_email"] = customer.get("email")

        # immagini prodotti
        for li in order["line_items"]:
            product_id = li.get("product_id")
            if product_id:
                p_res = requests.get(
                    f"https://{SHOP}/admin/api/{API_VERSION}/products/{product_id}.json",
                    headers=headers
                )
                p_data = p_res.json().get("product", {})
                li["image"] = ""
                if p_data.get("images"):
                    li["image"] = p_data["images"][0]["src"]

    return jsonify({"orders": orders})

# ---------------- MARK ORDER AS OPENED ----------------

@app.route("/api/mark_opened", methods=["POST"])
def mark_opened():
    order_id = request.json.get("order_id")

    if not order_id:
        return jsonify({"error": "Missing order_id"}), 400

    opened = load_opened()

    if order_id not in opened:
        opened.append(order_id)
        save_opened(opened)

    return jsonify({"status": "ok"})

@app.route("/api/unmark_opened", methods=["POST"])
def unmark_opened():
    order_id = request.json.get("order_id")

    if not order_id:
        return jsonify({"error": "Missing order_id"}), 400

    opened = load_opened()

    if order_id in opened:
        opened.remove(order_id)
        save_opened(opened)

    return jsonify({"status": "ok"})
# ---------------- RUN ----------------

if __name__ == "__main__":
    app.run(port=8000, debug=False)