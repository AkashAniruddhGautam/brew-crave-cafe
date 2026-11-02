import hmac
import io
import json
import os
import re
import secrets
import sqlite3
import time
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from functools import wraps
from pathlib import Path
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

from flask import Flask, g, jsonify, request, send_from_directory, session
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle
from werkzeug.security import check_password_hash, generate_password_hash
from waitress import serve


ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("CAFE_DATA_DIR", ROOT / "instance")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASE = DATA_DIR / "cafe.sqlite3"
SECRET_FILE = DATA_DIR / "secret.key"
TAX_PERCENT = 5
CAFE_TIME_ZONE = timezone(timedelta(hours=5, minutes=30), name="Asia/Kolkata")


def env_list(name):
    return {value.strip() for value in os.environ.get(name, "").split(",") if value.strip()}


ALLOWED_HOSTS = {"127.0.0.1", "localhost"}
ALLOWED_HOSTS.update(host.lower() for host in env_list("CAFE_ALLOWED_HOSTS"))
render_hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip().lower()
if render_hostname:
    ALLOWED_HOSTS.add(render_hostname)


def normalize_origin(origin):
    try:
        parsed = urlsplit(origin)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
            return None
        if parsed.path or parsed.query or parsed.fragment:
            return None
        return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"
    except ValueError:
        return None


ALLOWED_ORIGINS = {
    normalized
    for normalized in (normalize_origin(value) for value in env_list("CAFE_ALLOWED_ORIGINS"))
    if normalized
}

DEFAULT_MENU = [
    {"id": "menu-hot-coffee-classic", "name": "Hot Coffee (Classic)", "category": "Hot Coffee & Teas", "price_paise": 4900, "emoji": "☕", "art": "coffee", "type": "Hot coffee"},
    {"id": "menu-black-coffee", "name": "Black Coffee", "category": "Hot Coffee & Teas", "price_paise": 3900, "emoji": "☕", "art": "coffee", "type": "Hot coffee"},
    {"id": "menu-vanilla-coffee", "name": "Vanilla Coffee", "category": "Hot Coffee & Teas", "price_paise": 6900, "emoji": "☕", "art": "coffee", "type": "Hot coffee"},
    {"id": "menu-mocha-hot-coffee", "name": "Mocha Hot Coffee", "category": "Hot Coffee & Teas", "price_paise": 6900, "emoji": "☕", "art": "coffee", "type": "Hot coffee"},
    {"id": "menu-hazelnut-hot-coffee", "name": "Hazelnut Hot Coffee", "category": "Hot Coffee & Teas", "price_paise": 6900, "emoji": "☕", "art": "coffee", "type": "Hot coffee"},
    {"id": "menu-hot-chocolate", "name": "Hot Chocolate", "category": "Hot Coffee & Teas", "price_paise": 6900, "emoji": "🍫", "art": "coffee", "type": "Hot drink"},
    {"id": "menu-garam-kadak-chai", "name": "Garam Kadak Chai", "category": "Hot Coffee & Teas", "price_paise": 2000, "emoji": "🫖", "art": "tea", "type": "Chai"},
    {"id": "menu-kullad-chai", "name": "Kullad Chai", "category": "Hot Coffee & Teas", "price_paise": 2900, "emoji": "🫖", "art": "tea", "type": "Chai"},
    {"id": "menu-green-tea", "name": "Green Tea", "category": "Hot Coffee & Teas", "price_paise": 2900, "emoji": "🍵", "art": "tea", "type": "Tea"},
    {"id": "menu-regular-cold-coffee", "name": "Regular Cold Coffee", "category": "Cold Coffee & Shakes", "price_paise": 6900, "emoji": "🧋", "art": "cold", "type": "Cold coffee"},
    {"id": "menu-vanilla-cold-coffee", "name": "Vanilla Cold Coffee", "category": "Cold Coffee & Shakes", "price_paise": 7900, "emoji": "🧋", "art": "cold", "type": "Cold coffee"},
    {"id": "menu-mocha-cold-coffee", "name": "Mocha Cold Coffee", "category": "Cold Coffee & Shakes", "price_paise": 7900, "emoji": "🧋", "art": "cold", "type": "Cold coffee"},
    {"id": "menu-caramel-cold-coffee", "name": "Caramel Cold Coffee", "category": "Cold Coffee & Shakes", "price_paise": 7900, "emoji": "🧋", "art": "cold", "type": "Cold coffee"},
    {"id": "menu-hazelnut-cold-coffee", "name": "Hazelnut Cold Coffee", "category": "Cold Coffee & Shakes", "price_paise": 7900, "emoji": "🧋", "art": "cold", "type": "Cold coffee"},
    {"id": "menu-cold-chocolate-shake", "name": "Cold Chocolate Shake", "category": "Cold Coffee & Shakes", "price_paise": 11900, "emoji": "🥤", "art": "cold", "type": "Chocolate shake"},
    {"id": "menu-mint-mojito", "name": "Mint Mojito", "category": "Mojitos & Refreshers", "price_paise": 6900, "emoji": "🍃", "art": "cold", "type": "Mojito"},
    {"id": "menu-strawberry-mojito", "name": "Strawberry Mojito", "category": "Mojitos & Refreshers", "price_paise": 7900, "emoji": "🍓", "art": "cold", "type": "Mojito"},
    {"id": "menu-watermelon-mojito", "name": "Watermelon Mojito", "category": "Mojitos & Refreshers", "price_paise": 7900, "emoji": "🍉", "art": "cold", "type": "Mojito"},
    {"id": "menu-blueberry-mojito", "name": "Blueberry Mojito", "category": "Mojitos & Refreshers", "price_paise": 7900, "emoji": "🫐", "art": "cold", "type": "Mojito"},
    {"id": "menu-lemon-iced-tea", "name": "Lemon Iced Tea", "category": "Mojitos & Refreshers", "price_paise": 6900, "emoji": "🍋", "art": "cold", "type": "Iced tea"},
    {"id": "menu-peach-iced-tea", "name": "Peach Iced Tea", "category": "Mojitos & Refreshers", "price_paise": 6900, "emoji": "🍑", "art": "cold", "type": "Iced tea"},
    {"id": "menu-classic-bun-maska", "name": "Classic Bun Maska", "category": "Burgers & Buns", "price_paise": 4900, "emoji": "🍞", "art": "food", "type": "Bun"},
    {"id": "menu-aloo-tikki-burger-m", "name": "Classic Aloo Tikki Burger (M)", "category": "Burgers & Buns", "price_paise": 6900, "emoji": "🍔", "art": "food", "type": "Medium"},
    {"id": "menu-aloo-tikki-burger-l", "name": "Classic Aloo Tikki Burger (L)", "category": "Burgers & Buns", "price_paise": 8900, "emoji": "🍔", "art": "food", "type": "Large"},
    {"id": "menu-chicken-burger-m", "name": "Classic Chicken Burger (M)", "category": "Burgers & Buns", "price_paise": 8900, "emoji": "🍔", "art": "food", "type": "Medium"},
    {"id": "menu-chicken-burger-l", "name": "Classic Chicken Burger (L)", "category": "Burgers & Buns", "price_paise": 10900, "emoji": "🍔", "art": "food", "type": "Large"},
    {"id": "menu-sabudana-tikki-burger", "name": "Sabudana Tikki Burger", "category": "Burgers & Buns", "price_paise": 6900, "emoji": "🍔", "art": "food", "type": "Burger"},
    {"id": "menu-butter-garlic-bread", "name": "Butter Garlic Bread", "category": "Burgers & Buns", "price_paise": 6900, "emoji": "🥖", "art": "food", "type": "Garlic bread"},
    {"id": "menu-cheese-garlic-bread", "name": "Cheese Garlic Bread", "category": "Burgers & Buns", "price_paise": 8900, "emoji": "🥖", "art": "food", "type": "Garlic bread"},
    {"id": "menu-grilled-veg-sandwich", "name": "Grilled Veg Sandwich", "category": "Grilled Sandwiches", "price_paise": 8900, "emoji": "🥪", "art": "food", "type": "Sandwich"},
    {"id": "menu-grilled-cheese-sandwich", "name": "Grilled Cheese Sandwich", "category": "Grilled Sandwiches", "price_paise": 9900, "emoji": "🥪", "art": "food", "type": "Sandwich"},
    {"id": "menu-grilled-chicken-sandwich", "name": "Grilled Chicken Sandwich", "category": "Grilled Sandwiches", "price_paise": 12900, "emoji": "🥪", "art": "food", "type": "Sandwich"},
    {"id": "menu-plain-crispy-fries", "name": "Plain Crispy Fries", "category": "Fries & Quick Bites", "price_paise": 5900, "emoji": "🍟", "art": "food", "type": "Fries"},
    {"id": "menu-salted-french-fries", "name": "Salted French Fries", "category": "Fries & Quick Bites", "price_paise": 6900, "emoji": "🍟", "art": "food", "type": "Fries"},
    {"id": "menu-peri-peri-fries", "name": "Peri Peri Fries", "category": "Fries & Quick Bites", "price_paise": 6900, "emoji": "🍟", "art": "food", "type": "Fries"},
    {"id": "menu-crispy-veg-nuggets", "name": "Crispy Veg Nuggets (8pcs)", "category": "Fries & Quick Bites", "price_paise": 9900, "emoji": "🍟", "art": "food", "type": "8 pieces"},
    {"id": "menu-crispy-chicken-nuggets", "name": "Crispy Chicken Nuggets (8pcs)", "category": "Fries & Quick Bites", "price_paise": 11900, "emoji": "🍗", "art": "food", "type": "8 pieces"},
    {"id": "menu-plain-maggi", "name": "Plain Maggi", "category": "Maggi Corner", "price_paise": 4900, "emoji": "🍜", "art": "food", "type": "Maggi"},
    {"id": "menu-veg-masala-maggi", "name": "Veg Masala Maggi", "category": "Maggi Corner", "price_paise": 6900, "emoji": "🍜", "art": "food", "type": "Maggi"},
    {"id": "menu-cheese-burst-maggi", "name": "Cheese Burst Maggi", "category": "Maggi Corner", "price_paise": 7900, "emoji": "🍜", "art": "food", "type": "Maggi"},
]
LEGACY_MENU_IDS = (
    "cappuccino", "latte", "americano", "mocha", "iced-latte", "cold-brew",
    "lemonade", "matcha", "masala-chai", "croissant", "brownie", "sandwich",
)
LOGIN_ATTEMPTS = {}


def load_secret_key():
    if SECRET_FILE.exists():
        key = SECRET_FILE.read_bytes()
        if len(key) >= 32:
            return key
        raise RuntimeError(f"Session key is invalid; remove {SECRET_FILE} and restart.")
    key = secrets.token_bytes(48)
    with SECRET_FILE.open("xb") as secret_file:
        secret_file.write(key)
    try:
        os.chmod(SECRET_FILE, 0o600)
    except OSError:
        pass
    return key


app = Flask(__name__, static_folder=None)
cookie_samesite = os.environ.get("CAFE_COOKIE_SAMESITE", "Lax")
if cookie_samesite not in {"Lax", "Strict", "None"}:
    raise RuntimeError("CAFE_COOKIE_SAMESITE must be Lax, Strict, or None.")
is_hosted = bool(os.environ.get("RENDER") or os.environ.get("CAFE_HOSTED"))
app.config.update(
    SECRET_KEY=load_secret_key(),
    MAX_CONTENT_LENGTH=64 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE=cookie_samesite,
    SESSION_COOKIE_SECURE=os.environ.get("CAFE_COOKIE_SECURE", "true" if is_hosted else "false").lower() == "true",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    TRUSTED_HOSTS=sorted(ALLOWED_HOSTS),
)


def connect_db():
    connection = sqlite3.connect(DATABASE, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    return connection


@contextmanager
def db_connection():
    connection = connect_db()
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_db():
    with db_connection() as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('owner', 'staff')),
                active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                public_id TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                mode TEXT NOT NULL CHECK (mode IN ('Dine in', 'Takeaway')),
                payment TEXT NOT NULL CHECK (payment IN ('Cash', 'UPI', 'Card')),
                subtotal_paise INTEGER NOT NULL,
                tax_paise INTEGER NOT NULL,
                total_paise INTEGER NOT NULL,
                created_by INTEGER NOT NULL REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY,
                order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                product_id TEXT NOT NULL,
                product_name TEXT NOT NULL,
                price_paise INTEGER NOT NULL,
                quantity INTEGER NOT NULL CHECK (quantity BETWEEN 1 AND 99)
            );
            CREATE TABLE IF NOT EXISTS products (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                price_paise INTEGER NOT NULL CHECK (price_paise > 0),
                emoji TEXT NOT NULL,
                art TEXT NOT NULL CHECK (art IN ('coffee', 'cold', 'tea', 'food')),
                type TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS app_migrations (
                id TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            );
            """
        )
        if connection.execute("SELECT 1 FROM app_migrations WHERE id = 'brew-crave-pdf-menu-v1'").fetchone() is None:
            now = datetime.now(timezone.utc).isoformat()
            connection.executemany("DELETE FROM products WHERE id = ?", [(item_id,) for item_id in LEGACY_MENU_IDS])
            connection.executemany(
                "INSERT INTO products (id, name, category, price_paise, emoji, art, type, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (item["id"], item["name"], item["category"], item["price_paise"], item["emoji"], item["art"], item["type"], now, now)
                    for item in DEFAULT_MENU
                ],
            )
            connection.execute(
                "INSERT INTO app_migrations (id, applied_at) VALUES ('brew-crave-pdf-menu-v1', ?)",
                (now,),
            )


def api_error(message, status):
    return jsonify({"error": message}), status


def current_server_time():
    return datetime.now(CAFE_TIME_ZONE).isoformat(timespec="milliseconds")


def request_json():
    if not request.is_json:
        return None
    try:
        value = request.get_json(silent=False)
    except (ValueError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def user_summary(row):
    return {"id": row["id"], "username": row["username"], "role": row["role"], "active": bool(row["active"])}


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return api_error("Please sign in to continue.", 401)
        with db_connection() as connection:
            row = connection.execute(
                "SELECT id, username, role, active FROM users WHERE id = ?",
                (session["user_id"],),
            ).fetchone()
        if row is None or not row["active"]:
            session.clear()
            return api_error("This account is inactive. Ask the owner for access.", 401)
        g.user = row
        return view(*args, **kwargs)
    return wrapped


def owner_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if g.user["role"] != "owner":
            return api_error("Owner access is required for staff management.", 403)
        return view(*args, **kwargs)
    return wrapped


def csrf_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        supplied = request.headers.get("X-CSRF-Token", "")
        expected = session.get("csrf_token", "")
        if not supplied or not expected or not hmac.compare_digest(supplied, expected):
            return api_error("Your session expired. Refresh and sign in again.", 403)
        return view(*args, **kwargs)
    return wrapped


@app.before_request
def enforce_local_request():
    host = request.host.split(":", 1)[0].strip("[]").lower()
    if host not in ALLOWED_HOSTS:
        return api_error("This host is not configured for the cafe app.", 400)
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("Origin")
        if origin:
            normalized_origin = normalize_origin(origin)
            local_same_origin = (
                normalized_origin is not None
                and urlsplit(normalized_origin).hostname in {"127.0.0.1", "localhost"}
                and urlsplit(normalized_origin).netloc == request.host.lower()
            )
            if normalized_origin not in ALLOWED_ORIGINS and not local_same_origin:
                return api_error("Cross-origin requests are not allowed.", 403)


@app.after_request
def set_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; "
        "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    )
    return response


def username_is_valid(username):
    return isinstance(username, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,31}", username) is not None


def password_is_valid(password):
    return isinstance(password, str) and 12 <= len(password) <= 256


def product_summary(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "category": row["category"],
        "price": row["price_paise"] / 100,
        "emoji": row["emoji"],
        "art": row["art"],
        "type": row["type"],
        "active": bool(row["active"]),
    }


def validate_product(data):
    if not isinstance(data, dict):
        return None, "A valid product is required."
    text_fields = {
        "name": (data.get("name"), 1, 60),
        "category": (data.get("category"), 1, 32),
        "emoji": (data.get("emoji"), 1, 8),
        "type": (data.get("type"), 1, 40),
    }
    clean = {}
    for field, (value, minimum, maximum) in text_fields.items():
        if not isinstance(value, str):
            return None, f"{field.capitalize()} is required."
        value = value.strip()
        if not minimum <= len(value) <= maximum or any(ord(char) < 32 for char in value):
            return None, f"{field.capitalize()} must be between {minimum} and {maximum} characters."
        clean[field] = value
    art = data.get("art")
    if art not in {"coffee", "cold", "tea", "food"}:
        return None, "Choose a valid product style."
    try:
        raw_price = Decimal(str(data.get("price")))
        if not raw_price.is_finite():
            return None, "Enter a valid product price."
        price = raw_price.quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None, "Enter a valid product price."
    if raw_price != price:
        return None, "Price can have no more than two decimal places."
    if price < Decimal("0.01") or price > Decimal("999999.99"):
        return None, "Price must be between ₹0.01 and ₹999,999.99."
    clean["price_paise"] = int(price * 100)
    clean["art"] = art
    return clean, None


@app.get("/")
@app.get("/admin")
def index():
    return send_from_directory(ROOT, "index.html")


@app.get("/app.css")
def stylesheet():
    return send_from_directory(ROOT, "app.css")


@app.get("/app.js")
def client_script():
    return send_from_directory(ROOT, "app.js")


@app.get("/api/bootstrap")
def bootstrap_status():
    with db_connection() as connection:
        exists = connection.execute("SELECT 1 FROM users WHERE role = 'owner' LIMIT 1").fetchone()
    return jsonify({"setup_required": exists is None, "server_time": current_server_time()})


@app.get("/api/clock")
def clock():
    return jsonify({"server_time": current_server_time(), "time_zone": "Asia/Kolkata"})


@app.post("/api/setup")
def setup_owner():
    data = request_json()
    if data is None or not username_is_valid(data.get("username")):
        return api_error("Username must be 3–32 letters, numbers, dots, dashes or underscores.", 400)
    if not password_is_valid(data.get("password")):
        return api_error("Use a password with at least 12 characters.", 400)
    try:
        with db_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute("SELECT 1 FROM users WHERE role = 'owner' LIMIT 1").fetchone():
                return api_error("Owner setup has already been completed.", 409)
            cursor = connection.execute(
                "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, 'owner', ?)",
                (data["username"].strip(), generate_password_hash(data["password"]), datetime.now(timezone.utc).isoformat()),
            )
            user_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        return api_error("That username is already in use.", 409)
    session.clear()
    session.permanent = True
    session["user_id"] = user_id
    session["csrf_token"] = secrets.token_urlsafe(32)
    return jsonify({
        "user": {"id": user_id, "username": data["username"].strip(), "role": "owner"},
        "csrf_token": session["csrf_token"],
        "server_time": current_server_time(),
    }), 201


@app.post("/api/login")
def login():
    address = request.remote_addr or "local"
    now = time.monotonic()
    attempts, blocked_until = LOGIN_ATTEMPTS.get(address, (0, 0))
    if blocked_until > now:
        return api_error("Too many sign-in attempts. Wait 15 minutes and try again.", 429)
    data = request_json()
    username = data.get("username", "") if data else ""
    password = data.get("password", "") if data else ""
    if not isinstance(username, str) or not isinstance(password, str) or len(username) > 32 or len(password) > 256:
        return api_error("Username or password is incorrect.", 401)
    with db_connection() as connection:
        row = connection.execute(
            "SELECT id, username, password_hash, role, active FROM users WHERE username = ? COLLATE NOCASE",
            (username.strip(),),
        ).fetchone()
    if row is None or not row["active"] or not check_password_hash(row["password_hash"], password):
        attempts += 1
        LOGIN_ATTEMPTS[address] = (attempts, now + 900 if attempts >= 5 else 0)
        return api_error("Username or password is incorrect.", 401)
    LOGIN_ATTEMPTS.pop(address, None)
    session.clear()
    session.permanent = True
    session["user_id"] = row["id"]
    session["csrf_token"] = secrets.token_urlsafe(32)
    return jsonify({"user": user_summary(row), "csrf_token": session["csrf_token"], "server_time": current_server_time()})


@app.get("/api/me")
@login_required
def current_user():
    return jsonify({"user": user_summary(g.user), "csrf_token": session["csrf_token"], "server_time": current_server_time()})


@app.post("/api/logout")
@csrf_required
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.get("/api/menu")
@login_required
def menu():
    with db_connection() as connection:
        products = connection.execute("SELECT * FROM products WHERE active = 1 ORDER BY category, name COLLATE NOCASE").fetchall()
    return jsonify([product_summary(item) for item in products])


@app.get("/api/products")
@owner_required
def list_products():
    with db_connection() as connection:
        products = connection.execute("SELECT * FROM products ORDER BY category COLLATE NOCASE, name COLLATE NOCASE").fetchall()
    return jsonify([product_summary(item) for item in products])


@app.post("/api/products")
@csrf_required
@owner_required
def create_product():
    data = request_json()
    product, error = validate_product(data)
    if error:
        return api_error(error, 400)
    product_id = f"custom-{secrets.token_hex(8)}"
    now = datetime.now(timezone.utc).isoformat()
    with db_connection() as connection:
        connection.execute(
            "INSERT INTO products (id, name, category, price_paise, emoji, art, type, active, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (product_id, product["name"], product["category"], product["price_paise"], product["emoji"], product["art"], product["type"], now, now),
        )
        row = connection.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    return jsonify(product_summary(row)), 201


@app.put("/api/products/<product_id>")
@csrf_required
@owner_required
def update_product(product_id):
    data = request_json()
    product, error = validate_product(data)
    if error:
        return api_error(error, 400)
    now = datetime.now(timezone.utc).isoformat()
    with db_connection() as connection:
        cursor = connection.execute(
            "UPDATE products SET name = ?, category = ?, price_paise = ?, emoji = ?, art = ?, type = ?, updated_at = ? WHERE id = ?",
            (product["name"], product["category"], product["price_paise"], product["emoji"], product["art"], product["type"], now, product_id),
        )
        if cursor.rowcount == 0:
            return api_error("Product was not found.", 404)
        row = connection.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    return jsonify(product_summary(row))


@app.patch("/api/products/<product_id>")
@csrf_required
@owner_required
def set_product_active(product_id):
    data = request_json()
    if data is None or type(data.get("active")) is not bool:
        return api_error("Choose whether the product should be available.", 400)
    with db_connection() as connection:
        cursor = connection.execute("UPDATE products SET active = ?, updated_at = ? WHERE id = ?", (int(data["active"]), datetime.now(timezone.utc).isoformat(), product_id))
        if cursor.rowcount == 0:
            return api_error("Product was not found.", 404)
        row = connection.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    return jsonify(product_summary(row))


def serialize_order(order_row, items):
    return {
        "id": order_row["public_id"],
        "timestamp": order_row["created_at"],
        "mode": order_row["mode"],
        "payment": order_row["payment"],
        "subtotal": order_row["subtotal_paise"] / 100,
        "tax": order_row["tax_paise"] / 100,
        "total": order_row["total_paise"] / 100,
        "items": [
            {"id": item["product_id"], "name": item["product_name"], "price": item["price_paise"] / 100, "quantity": item["quantity"]}
            for item in items
        ],
    }


def pdf_text(value):
    normalized = unicodedata.normalize("NFKD", str(value))
    return escape(normalized.encode("ascii", "replace").decode("ascii"))


def create_order_pdf(order_row, items):
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"Brew & Crave Cafe bill {order_row['public_id']}",
        author="Brew & Crave Cafe",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="CafeTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#315b42"),
        alignment=TA_CENTER,
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="CafeDetails",
        parent=styles["Normal"],
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#625f57"),
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name="BillMeta",
        parent=styles["Normal"],
        fontSize=10,
        leading=15,
    ))
    styles.add(ParagraphStyle(
        name="BillCell",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
    ))
    styles.add(ParagraphStyle(
        name="BillAmount",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        alignment=TA_RIGHT,
    ))
    styles.add(ParagraphStyle(
        name="BillTotal",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=15,
        alignment=TA_RIGHT,
    ))
    created_at = datetime.fromisoformat(order_row["created_at"]).astimezone(CAFE_TIME_ZONE)
    story = [
        Paragraph("Brew &amp; Crave Cafe", styles["CafeTitle"]),
        Paragraph("C4 G8A Shop, Janakpuri, New Delhi - 110058", styles["CafeDetails"]),
        Paragraph("Near Tihar Jail Gate Number 4", styles["CafeDetails"]),
        Spacer(1, 10 * mm),
        Paragraph(f"<b>Bill:</b> {pdf_text(order_row['public_id'])}", styles["BillMeta"]),
        Paragraph(f"<b>Date:</b> {created_at.strftime('%d %b %Y, %I:%M %p')} IST", styles["BillMeta"]),
        Paragraph(f"<b>Order:</b> {pdf_text(order_row['mode'])} &nbsp;&nbsp; <b>Paid via:</b> {pdf_text(order_row['payment'])}", styles["BillMeta"]),
        Spacer(1, 5 * mm),
    ]
    rows = [[
        Paragraph("<b>Item</b>", styles["BillCell"]),
        Paragraph("<b>Qty</b>", styles["BillAmount"]),
        Paragraph("<b>Price</b>", styles["BillAmount"]),
        Paragraph("<b>Amount</b>", styles["BillAmount"]),
    ]]
    for item in items:
        rows.append([
            Paragraph(pdf_text(item["product_name"]), styles["BillCell"]),
            Paragraph(str(item["quantity"]), styles["BillAmount"]),
            Paragraph(f"INR {item['price_paise'] / 100:,.2f}", styles["BillAmount"]),
            Paragraph(f"INR {item['price_paise'] * item['quantity'] / 100:,.2f}", styles["BillAmount"]),
        ])
    rows.extend([
        ["", "", Paragraph("Subtotal", styles["BillCell"]), Paragraph(f"INR {order_row['subtotal_paise'] / 100:,.2f}", styles["BillAmount"])],
        ["", "", Paragraph("GST (5%)", styles["BillCell"]), Paragraph(f"INR {order_row['tax_paise'] / 100:,.2f}", styles["BillAmount"])],
        ["", "", Paragraph("<b>Total paid</b>", styles["BillCell"]), Paragraph(f"INR {order_row['total_paise'] / 100:,.2f}", styles["BillTotal"])],
    ])
    table = LongTable(rows, colWidths=[80 * mm, 16 * mm, 34 * mm, 40 * mm], repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#edf4ec")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#315b42")),
        ("LINEBELOW", (0, 0), (-1, 0), 0.7, colors.HexColor("#b7c8b7")),
        ("LINEABOVE", (2, -3), (-1, -3), 0.5, colors.HexColor("#d9d4ca")),
        ("LINEABOVE", (2, -1), (-1, -1), 0.8, colors.HexColor("#315b42")),
        ("BACKGROUND", (2, -1), (-1, -1), colors.HexColor("#edf4ec")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.extend([table, Spacer(1, 8 * mm), Paragraph("Thank you for visiting Brew &amp; Crave Cafe!", styles["CafeDetails"])])
    document.build(story)
    return buffer.getvalue()


@app.get("/api/orders")
@login_required
def list_orders():
    with db_connection() as connection:
        orders = connection.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 100").fetchall()
        result = []
        for order in orders:
            items = connection.execute("SELECT * FROM order_items WHERE order_id = ? ORDER BY id", (order["id"],)).fetchall()
            result.append(serialize_order(order, items))
    return jsonify(result)


@app.get("/api/orders/<public_id>/pdf")
@login_required
def download_order_pdf(public_id):
    with db_connection() as connection:
        order = connection.execute("SELECT * FROM orders WHERE public_id = ?", (public_id,)).fetchone()
        if order is None:
            return api_error("Bill was not found.", 404)
        items = connection.execute(
            "SELECT * FROM order_items WHERE order_id = ? ORDER BY id",
            (order["id"],),
        ).fetchall()
    pdf = create_order_pdf(order, items)
    return app.response_class(
        pdf,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="Brew-and-Crave-{order["public_id"]}.pdf"'},
    )


@app.post("/api/orders")
@csrf_required
def create_order():
    data = request_json()
    if data is None:
        return api_error("A valid JSON order is required.", 400)
    if data.get("mode") not in {"Dine in", "Takeaway"} or data.get("payment") not in {"Cash", "UPI", "Card"}:
        return api_error("Choose a valid order type and payment method.", 400)
    requested_items = data.get("items")
    if not isinstance(requested_items, list) or not 1 <= len(requested_items) <= 50:
        return api_error("An order must contain between 1 and 50 menu items.", 400)
    quantities = {}
    for item in requested_items:
        if not isinstance(item, dict):
            return api_error("Order item is invalid.", 400)
        product_id = item.get("id")
        quantity = item.get("quantity")
        if not isinstance(product_id, str) or type(quantity) is not int or not 1 <= quantity <= 99:
            return api_error("Order contains an invalid menu item or quantity.", 400)
        quantities[product_id] = quantities.get(product_id, 0) + quantity
        if quantities[product_id] > 99:
            return api_error("A menu item quantity cannot exceed 99.", 400)
    now = datetime.now(timezone.utc).isoformat()
    with db_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        products = {}
        for item_id in quantities:
            product = connection.execute("SELECT * FROM products WHERE id = ? AND active = 1", (item_id,)).fetchone()
            if product is None:
                return api_error("An order contains a product that is no longer available.", 400)
            products[item_id] = product
        subtotal = sum(products[item_id]["price_paise"] * quantity for item_id, quantity in quantities.items())
        tax = (subtotal * TAX_PERCENT + 50) // 100
        cursor = connection.execute(
            "INSERT INTO orders (public_id, created_at, mode, payment, subtotal_paise, tax_paise, total_paise, created_by) VALUES ('pending', ?, ?, ?, ?, ?, ?, ?)",
            (now, data["mode"], data["payment"], subtotal, tax, subtotal + tax, g.user["id"]),
        )
        order_id = cursor.lastrowid
        public_id = f"LB-{order_id:06d}"
        connection.execute("UPDATE orders SET public_id = ? WHERE id = ?", (public_id, order_id))
        for item_id, quantity in quantities.items():
            product = products[item_id]
            connection.execute(
                "INSERT INTO order_items (order_id, product_id, product_name, price_paise, quantity) VALUES (?, ?, ?, ?, ?)",
                (order_id, item_id, product["name"], product["price_paise"], quantity),
            )
        order = connection.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        items = connection.execute("SELECT * FROM order_items WHERE order_id = ? ORDER BY id", (order_id,)).fetchall()
    return jsonify(serialize_order(order, items)), 201


@app.get("/api/users")
@owner_required
def list_users():
    with db_connection() as connection:
        rows = connection.execute("SELECT id, username, role, active FROM users ORDER BY role, username").fetchall()
    return jsonify([user_summary(row) for row in rows])


@app.post("/api/users")
@csrf_required
@owner_required
def create_staff():
    data = request_json()
    if data is None or not username_is_valid(data.get("username")):
        return api_error("Username must be 3–32 letters, numbers, dots, dashes or underscores.", 400)
    if not password_is_valid(data.get("password")):
        return api_error("Use a password with at least 12 characters.", 400)
    try:
        with db_connection() as connection:
            cursor = connection.execute(
                "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, 'staff', ?)",
                (data["username"].strip(), generate_password_hash(data["password"]), datetime.now(timezone.utc).isoformat()),
            )
            row = connection.execute("SELECT id, username, role, active FROM users WHERE id = ?", (cursor.lastrowid,)).fetchone()
    except sqlite3.IntegrityError:
        return api_error("That username is already in use.", 409)
    return jsonify(user_summary(row)), 201


@app.patch("/api/users/<int:user_id>")
@csrf_required
@owner_required
def update_staff(user_id):
    data = request_json()
    if data is None or type(data.get("active")) is not bool:
        return api_error("Choose whether the staff account should be active.", 400)
    with db_connection() as connection:
        row = connection.execute("SELECT id, username, role, active FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            return api_error("Staff account was not found.", 404)
        if row["role"] != "staff":
            return api_error("The owner account cannot be disabled here.", 400)
        connection.execute("UPDATE users SET active = ? WHERE id = ?", (int(data["active"]), user_id))
        updated = connection.execute("SELECT id, username, role, active FROM users WHERE id = ?", (user_id,)).fetchone()
    return jsonify(user_summary(updated))


@app.errorhandler(413)
def request_too_large(_error):
    return api_error("Request is too large.", 413)


@app.errorhandler(500)
def internal_error(_error):
    app.logger.exception("Unhandled server error")
    return api_error("Something went wrong. Check the local server log.", 500)


initialize_db()

if __name__ == "__main__" and not is_hosted:
    port = int(os.environ.get("CAFE_PORT", "8000"))
    print(f"Brew & Crave Cafe billing is available at http://127.0.0.1:{port}")
    serve(app, host="127.0.0.1", port=port, threads=8, connection_limit=100, channel_timeout=30)
