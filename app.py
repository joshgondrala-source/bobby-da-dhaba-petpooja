from flask import Flask, render_template, request, session, redirect, abort, jsonify
from datetime import datetime
from functools import wraps
import os
import sqlite3
import threading
import time
from urllib.parse import parse_qs, urlparse
from dotenv import load_dotenv

load_dotenv()  # reads .env in the project root (if present) into os.environ

from petpooja_client import PetPoojaClient, PetPoojaError
from menu_sync import normalize_petpooja_menu, build_restaurant_menu, load_category_map

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
DB_PATH = os.path.join(app.root_path, "restaurant.db")
# Set explicitly (rather than relying on the debug= kwarg passed to app.run())
# so the settlement-poller startup check below sees the right value even
# though it runs at import time, before app.run() is ever called — this
# matters for gunicorn (Phase 8), which imports this module and never calls
# app.run() at all. Set FLASK_DEBUG=0 in production (e.g. on Render).
app.debug = os.environ.get("FLASK_DEBUG", "1") == "1"

# Shared secret for the /admin/* routes (menu sync, settlement poll trigger).
# Set ADMIN_TOKEN as a real env var before deploying — with no token
# configured we fall back to blocking access entirely rather than leaving
# these routes wide open (see require_admin_token below).
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN")


def require_admin_token(view_func):
    """Guards /admin/* routes with a shared-secret token, since this app has
    no manager/owner login of its own. Pass it as either the `token` query
    param or an `X-Admin-Token` header."""
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not ADMIN_TOKEN:
            abort(503, description="ADMIN_TOKEN is not configured on the server.")

        supplied = request.args.get("token") or request.headers.get("X-Admin-Token")

        if supplied != ADMIN_TOKEN:
            abort(401, description="Invalid or missing admin token.")

        return view_func(*args, **kwargs)

    return wrapped


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_db_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tables (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_number INTEGER NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'AVAILABLE' CHECK (status IN ('AVAILABLE', 'OCCUPIED')),
                occupied_since TEXT,
                customer_name TEXT,
                customer_phone TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS table_cart_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_id INTEGER NOT NULL,
                item_name TEXT NOT NULL,
                unit_price INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                instructions TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (table_id) REFERENCES tables(id)
            );

            CREATE TABLE IF NOT EXISTS kots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kot_number INTEGER UNIQUE,
                table_id INTEGER NOT NULL,
                kot_type TEXT NOT NULL CHECK (kot_type IN ('NEW TABLE', 'RUNNING TABLE')),
                payment_status TEXT NOT NULL DEFAULT 'UNPAID' CHECK (payment_status IN ('UNPAID', 'PAID')),
                petpooja_order_id TEXT,
                push_status TEXT NOT NULL DEFAULT 'PENDING' CHECK (push_status IN ('PENDING', 'SENT', 'FAILED', 'CANCELLED')),
                push_error TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (table_id) REFERENCES tables(id)
            );

            CREATE TABLE IF NOT EXISTS kot_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kot_id INTEGER NOT NULL,
                item_name TEXT NOT NULL,
                unit_price INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                instructions TEXT,
                FOREIGN KEY (kot_id) REFERENCES kots(id)
            );

            CREATE TABLE IF NOT EXISTS counters (
                name TEXT PRIMARY KEY,
                value INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS petpooja_items (
                petpooja_item_id TEXT PRIMARY KEY,
                petpooja_category_id TEXT,
                petpooja_category_name TEXT,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                is_veg INTEGER NOT NULL DEFAULT 1,
                active INTEGER NOT NULL DEFAULT 1,
                synced_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO counters (name, value) VALUES ('takeaway_token', 0)"
        )

        # Migrations for columns added after the original DB file was created —
        # CREATE TABLE IF NOT EXISTS above won't add columns to a pre-existing table.
        existing_table_cols = {row["name"] for row in conn.execute("PRAGMA table_info(tables)")}
        if "customer_name" not in existing_table_cols:
            conn.execute("ALTER TABLE tables ADD COLUMN customer_name TEXT")
        if "customer_phone" not in existing_table_cols:
            conn.execute("ALTER TABLE tables ADD COLUMN customer_phone TEXT")

        existing_kot_cols = {row["name"] for row in conn.execute("PRAGMA table_info(kots)")}
        if "petpooja_order_id" not in existing_kot_cols:
            conn.execute("ALTER TABLE kots ADD COLUMN petpooja_order_id TEXT")
        if "push_status" not in existing_kot_cols:
            conn.execute("ALTER TABLE kots ADD COLUMN push_status TEXT NOT NULL DEFAULT 'PENDING'")
        if "push_error" not in existing_kot_cols:
            conn.execute("ALTER TABLE kots ADD COLUMN push_error TEXT")

        conn.commit()


init_db()

petpooja_client = PetPoojaClient()


def save_petpooja_items_to_db(normalized_items):
    with get_db_connection() as conn:
        conn.executemany(
            """
            INSERT INTO petpooja_items
                (petpooja_item_id, petpooja_category_id, petpooja_category_name, name, price, is_veg, active, synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(petpooja_item_id) DO UPDATE SET
                petpooja_category_id = excluded.petpooja_category_id,
                petpooja_category_name = excluded.petpooja_category_name,
                name = excluded.name,
                price = excluded.price,
                is_veg = excluded.is_veg,
                active = excluded.active,
                synced_at = CURRENT_TIMESTAMP
            """,
            [
                (
                    item["petpooja_item_id"],
                    item["petpooja_category_id"],
                    item["petpooja_category_name"],
                    item["name"],
                    item["price"],
                    1 if item["is_veg"] else 0,
                    1 if item["active"] else 0,
                )
                for item in normalized_items
            ]
        )
        conn.commit()


def load_petpooja_items_from_db():
    with get_db_connection() as conn:
        rows = conn.execute("SELECT * FROM petpooja_items").fetchall()

    return [
        {
            "petpooja_item_id": row["petpooja_item_id"],
            "petpooja_category_id": row["petpooja_category_id"] or "",
            "petpooja_category_name": row["petpooja_category_name"] or "",
            "name": row["name"],
            "price": row["price"],
            "is_veg": bool(row["is_veg"]),
            "active": bool(row["active"]),
        }
        for row in rows
    ]


def sync_menu_from_petpooja():
    """
    Pulls the live menu from PetPooja, persists it locally, and returns
    (normalized_items, raw_categories_seen) so the caller/admin route can
    report which PetPooja category ids still need mapping in category_map.json.
    Raises PetPoojaError if credentials are missing or the call fails.
    """
    raw = petpooja_client.fetch_menu()
    normalized_items = normalize_petpooja_menu(raw)
    save_petpooja_items_to_db(normalized_items)

    raw_categories_seen = sorted({
        (item["petpooja_category_id"], item["petpooja_category_name"])
        for item in normalized_items
        if item["petpooja_category_id"]
    })

    return normalized_items, raw_categories_seen


def build_active_menu():
    """
    Builds the menu the app should render right now:
      1. If we have any locally cached PetPooja items (from a previous
         successful sync) AND category_map.json maps at least one category,
         merge PetPooja items on top of the fallback menu category-by-category.
      2. Otherwise, use the original hardcoded FALLBACK_MENU untouched — this
         keeps local development working before PetPooja is wired up.
    """
    category_map = load_category_map()
    category_map = {k: v for k, v in category_map.items() if not k.startswith("_")}

    cached_items = load_petpooja_items_from_db()

    menu = {key: list(items) for key, items in FALLBACK_MENU.items()}

    if cached_items and any(category_map.values()):
        petpooja_menu = build_restaurant_menu(cached_items, category_map)
        for category_key, items in petpooja_menu.items():
            if items:
                menu[category_key] = items

    return menu


def refresh_menu_globals():
    global restaurant_menu, MENU_LOOKUP, MENU_LOOKUP_ITEMS
    restaurant_menu = build_active_menu()
    MENU_LOOKUP = {
        item["name"]: item["price"]
        for category_items in restaurant_menu.values()
        for item in category_items
    }
    MENU_LOOKUP_ITEMS = {
        item["name"]: item
        for category_items in restaurant_menu.values()
        for item in category_items
    }


def get_or_create_table_id(table_number):
    table_key = (table_number or "").strip()

    if not table_key:
        return None

    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT id FROM tables WHERE table_number = ?",
            (table_key,)
        ).fetchone()

        if row:
            return row["id"]

        cursor = conn.execute(
            "INSERT INTO tables (table_number) VALUES (?)",
            (table_key,)
        )
        conn.commit()

        return cursor.lastrowid


def get_table_customer_info(table_id):
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT customer_name, customer_phone FROM tables WHERE id = ?",
            (table_id,)
        ).fetchone()

    if not row:
        return None

    if not row["customer_name"] or not row["customer_phone"]:
        return None

    return {"name": row["customer_name"], "phone": row["customer_phone"]}


def save_table_customer_info(table_id, name, phone):
    with get_db_connection() as conn:
        conn.execute(
            """
            UPDATE tables
            SET customer_name = ?, customer_phone = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (name, phone, table_id)
        )
        conn.commit()


def clear_table_customer_info(table_id):
    with get_db_connection() as conn:
        conn.execute(
            "UPDATE tables SET customer_name = NULL, customer_phone = NULL WHERE id = ?",
            (table_id,)
        )
        conn.commit()


def resolve_table_value():
    table = request.form.get("table")

    if not table:
        table = request.args.get("table")

    if not table and request.referrer:
        ref_query = parse_qs(urlparse(request.referrer).query)
        table_from_ref = ref_query.get("table", [None])[0]
        if table_from_ref:
            table = table_from_ref

    if not table:
        # Per-browser fallback (session cookie) instead of a shared global,
        # so one customer's table never leaks into another customer's session.
        table = session.get("table")

    table = (table or "").strip() or None

    if table:
        session["table"] = table

    return table


def get_table_cart_items(table_id):
    with get_db_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                id,
                item_name AS name,
                unit_price AS price,
                quantity,
                COALESCE(instructions, '') AS instructions
            FROM table_cart_items
            WHERE table_id = ?
            ORDER BY id ASC
            """,
            (table_id,)
        ).fetchall()

    return [dict(row) for row in rows]


def format_table_timestamp(value):
    if not value:
        return ""

    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").strftime("%d %b %Y, %I:%M %p")
    except (ValueError, TypeError):
        return value


def describe_order_status(payment_status, push_status):
    """
    Translates internal bookkeeping fields (payment_status/push_status) into a
    single customer-friendly status — customers should never see internal
    jargon like "NEW TABLE"/"RUNNING TABLE" (that's just KOT print grouping)
    or raw enum values.
    """
    if push_status == "CANCELLED":
        return {"label": "Cancelled", "emoji": "❌", "tone": "cancelled"}
    if push_status == "FAILED":
        return {"label": "Confirm with counter", "emoji": "⚠️", "tone": "warning"}
    if push_status == "PENDING":
        return {"label": "Confirming with kitchen", "emoji": "⏳", "tone": "warning"}
    if payment_status == "PAID":
        return {"label": "Paid", "emoji": "💰", "tone": "paid"}
    return {"label": "Sent to kitchen", "emoji": "✅", "tone": "sent"}


def get_table_order_history(table_id):
    with get_db_connection() as conn:
        kot_rows = conn.execute(
            """
            SELECT
                k.id,
                k.kot_number,
                k.payment_status,
                k.push_status,
                k.created_at,
                COALESCE(SUM(ki.unit_price * ki.quantity), 0) AS total
            FROM kots k
            LEFT JOIN kot_items ki ON ki.kot_id = k.id
            WHERE k.table_id = ?
              AND k.created_at >= (
                  SELECT COALESCE(occupied_since, '9999-12-31 23:59:59')
                  FROM tables
                  WHERE id = k.table_id
              )
            GROUP BY k.id, k.kot_number, k.payment_status, k.push_status, k.created_at
            ORDER BY k.id ASC
            """,
            (table_id,)
        ).fetchall()

        orders = []

        for kot in kot_rows:
            item_rows = conn.execute(
                """
                SELECT item_name, quantity, COALESCE(instructions, '') AS instructions
                FROM kot_items
                WHERE kot_id = ?
                ORDER BY id ASC
                """,
                (kot["id"],)
            ).fetchall()

            orders.append({
                "order_id": kot["kot_number"],
                "status": describe_order_status(kot["payment_status"], kot["push_status"]),
                "time": format_table_timestamp(kot["created_at"]),
                "total": float(kot["total"]),
                "items": [
                    {
                        "name": item["item_name"],
                        "quantity": item["quantity"],
                        "instructions": item["instructions"]
                    }
                    for item in item_rows
                ]
            })

    return orders


def get_table_bill_summary(table_id):
    with get_db_connection() as conn:
        unpaid_rows = conn.execute(
            """
            SELECT
                k.id,
                k.kot_number,
                k.created_at,
                COALESCE(SUM(ki.unit_price * ki.quantity), 0) AS total
            FROM kots k
            LEFT JOIN kot_items ki ON ki.kot_id = k.id
            WHERE k.table_id = ? AND k.payment_status = 'UNPAID'
            GROUP BY k.id, k.kot_number, k.created_at
            ORDER BY k.id ASC
            """,
            (table_id,)
        ).fetchall()

    orders = [
        {
            "order_id": row["kot_number"],
            "time": format_table_timestamp(row["created_at"]),
            "total": float(row["total"])
        }
        for row in unpaid_rows
    ]

    food_total = sum(order["total"] for order in orders)
    gst = round(food_total * 0.05, 2)
    grand_total = round(food_total + gst, 2)
    rounded_total = round(grand_total)

    return {
        "orders": orders,
        "food_total": food_total,
        "gst": gst,
        "grand_total": grand_total,
        "rounded_total": rounded_total,
    }


def settle_and_clear_table(table_id):
    """
    Called once PetPooja reports a table's bill as settled. Marks all of the
    table's KOTs PAID and resets the table so the next customer who enters
    this table number gets a clean menu with no leftover orders/bill/customer
    info from the previous guest.
    """
    with get_db_connection() as conn:
        conn.execute(
            "UPDATE kots SET payment_status = 'PAID' WHERE table_id = ? AND payment_status = 'UNPAID'",
            (table_id,)
        )
        conn.execute(
            "DELETE FROM table_cart_items WHERE table_id = ?",
            (table_id,)
        )
        conn.execute(
            """
            UPDATE tables
            SET status = 'AVAILABLE', occupied_since = NULL, customer_name = NULL, customer_phone = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (table_id,)
        )
        conn.commit()


# Statuses PetPooja might report for an order. PLACEHOLDER — correct once
# real docs are available (see PETPOOJA_SETUP.md).
PETPOOJA_SETTLED_STATUSES = {"settled", "paid", "closed", "complete", "completed", "5"}
# Manager voided/cancelled the KOT in PetPooja (e.g. item unavailable, customer
# walked out without paying) — no money owed, but the table should still free
# up locally instead of staying stuck "OCCUPIED" forever.
PETPOOJA_CANCELLED_STATUSES = {"cancelled", "canceled", "void", "voided", "rejected"}


def poll_petpooja_settlements():
    """
    Phase 5: since PetPooja has no push webhook for "table settled" for 3rd
    party apps, we poll instead. For every order we've sent to PetPooja and
    is still marked unpaid locally, ask PetPooja for its current status:
      - settled/paid  -> mark that order PAID locally (bill was paid)
      - cancelled/void -> mark that order PAID locally too (nothing owed —
        e.g. item unavailable and customer left without ordering anything
        else), just tagged with push_status='CANCELLED' for the record
      - anything else  -> leave alone, still genuinely in progress
    Once a table has zero remaining UNPAID orders (whether resolved by
    payment or cancellation), the table is auto-cleared locally so the next
    customer sitting there gets a clean slate.
    Runs on a background thread every interval. Never raises — a PetPooja
    hiccup should not crash the poller loop.
    """
    if not petpooja_client.is_configured():
        return

    with get_db_connection() as conn:
        kot_rows = conn.execute(
            """
            SELECT id, table_id, petpooja_order_id
            FROM kots
            WHERE payment_status = 'UNPAID' AND push_status = 'SENT'
            """
        ).fetchall()

    tables_touched = set()

    for kot_row in kot_rows:
        order_id = kot_row["petpooja_order_id"]

        if not order_id:
            continue

        try:
            status_response = petpooja_client.get_order_status(order_id)
        except PetPoojaError as exc:
            print(f"[petpooja-poll] status check failed for order {order_id}: {exc}")
            continue

        status_value = str(status_response.get("status", "")).strip().lower()  # PLACEHOLDER field name

        if status_value in PETPOOJA_SETTLED_STATUSES:
            with get_db_connection() as conn:
                conn.execute(
                    "UPDATE kots SET payment_status = 'PAID' WHERE id = ?",
                    (kot_row["id"],)
                )
                conn.commit()
            tables_touched.add(kot_row["table_id"])
        elif status_value in PETPOOJA_CANCELLED_STATUSES:
            with get_db_connection() as conn:
                conn.execute(
                    "UPDATE kots SET payment_status = 'PAID', push_status = 'CANCELLED' WHERE id = ?",
                    (kot_row["id"],)
                )
                conn.commit()
            tables_touched.add(kot_row["table_id"])
            print(f"[petpooja-poll] order {order_id} was cancelled/voided in PetPooja")

    for table_id in tables_touched:
        with get_db_connection() as conn:
            remaining = conn.execute(
                "SELECT COUNT(*) AS count FROM kots WHERE table_id = ? AND payment_status = 'UNPAID'",
                (table_id,)
            ).fetchone()

        if remaining["count"] == 0:
            settle_and_clear_table(table_id)
            print(f"[petpooja-poll] table_id={table_id} fully resolved in PetPooja — cleared locally")


def start_settlement_poller(interval_seconds=20):
    """Starts the background polling thread once (guarded against the Flask
    debug reloader, which otherwise spawns two processes and would start the
    poller twice)."""
    is_reloader_child = os.environ.get("WERKZEUG_RUN_MAIN") == "true"

    if app.debug and not is_reloader_child:
        return  # this is the reloader's parent watcher process, not the real app

    def _loop():
        while True:
            time.sleep(interval_seconds)
            try:
                poll_petpooja_settlements()
            except Exception as exc:  # keep the poller alive no matter what
                print(f"[petpooja-poll] unexpected error: {exc}")

    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()

# FALLBACK MENU DATA — used until PetPooja is synced & category_map.json is filled in.
FALLBACK_MENU = {
   "veg_soups": [
{"name": "Sweet Corn Soup Veg", "price": 99},
{"name": "Hot N Sour Veg", "price": 99},
{"name": "Lemon Coriander Soup", "price": 99},
{"name": "Noodles Soup Veg", "price": 99},
{"name": "Veg Manchow Soup", "price": 99}
],

"veg_starters": [
{"name": "Aloo 65", "price": 169},
{"name": "Honey Chilli Potato", "price": 199},
{"name": "Gobi Manchurian", "price": 189},
{"name": "Chilli Babycorn", "price": 229},
{"name": "Babycorn 65", "price": 229},
{"name": "Paneer 65", "price": 249},
{"name": "Chilli Paneer", "price": 249},
{"name": "Veg Manchurian", "price": 189},
{"name": "Chilli Gobi", "price": 179},
{"name": "Golden Crispy Corn", "price": 249},
{"name": "Paneer Majestic", "price": 259},
{"name": "Chilli Mushroom", "price": 239},
{"name": "Onion Rings", "price": 179},
{"name": "Creamy Paneer", "price": 169}
],

"veg_tikka": [
{"name": "Paneer Tikka", "price": 299}
],

"veg_curries": [
{"name": "Mix Veg Curry", "price": 189},
{"name": "Jeera Wale Aloo", "price": 189},
{"name": "Aloo Gobi", "price": 189},
{"name": "Gobi Mutter", "price": 189},
{"name": "Shahi Paneer", "price": 329},
{"name": "Paneer Butter Masala", "price": 249},
{"name": "Paneer Lababdar", "price": 249},
{"name": "Malai Kofta", "price": 229},
{"name": "Dum Aloo", "price": 299},
{"name": "Paneer Tikka Masala", "price": 329},
{"name": "Paneer Bhurji", "price": 329},
{"name": "Kaju Paneer", "price": 329},
{"name": "Mutter Paneer", "price": 249},
{"name": "Kadhai Paneer", "price": 249},
{"name": "Kaju Tomato", "price": 289}
],

"dal": [
{"name": "Tomato Dal", "price": 149},
{"name": "Dal Fry", "price": 149},
{"name": "Tadka Wali Dal", "price": 179}
],

"veg_biryani": [
{"name": "Veg Biryani", "price": 229},
{"name": "Paneer Biryani", "price": 249},
{"name": "Mushroom Biryani", "price": 249},
{"name": "Kaju Biryani", "price": 259}
],

"veg_chinese": [
{"name": "Veg Noodles", "price": 159},
{"name": "Veg Fried Rice", "price": 169},
{"name": "Veg Schezwan Noodles", "price": 169},
{"name": "Veg Schezwan Rice", "price": 179},
{"name": "Veg Chilli Garlic Rice", "price": 179},
{"name": "Paneer Fried Rice", "price": 199},
{"name": "Kaju Rice", "price": 199},
{"name": "Kaju Paneer Fried Rice", "price": 249}
],

"veg_combos": [
{"name": "Veg Fried Rice + Veg Manchurian Gravy", "price": 269},
{"name": "Veg Noodles + Veg Manchurian Gravy", "price": 269}
],

"veg_rice": [
{"name": "Plain Rice", "price": 99},
{"name": "Jeera Rice", "price": 159},
{"name": "Green Peas Pulao", "price": 179},
{"name": "Curd Rice", "price": 179}
],

"veg_parathas": [
{"name": "Aloo Paratha", "price": 119},
{"name": "Onion Paratha", "price": 119},
{"name": "Paneer Paratha", "price": 179},
{"name": "Gobi Paratha", "price": 119},
{"name": "Lachha Paratha", "price": 119}
],
"nonveg_soups": [
{"name": "Chicken Sweet Corn Soup", "price": 139},
{"name": "Chicken Noodles Soup", "price": 139},
{"name": "Chicken Hot N Sour Soup", "price": 139},
{"name": "Chicken Manchow Soup", "price": 139},
{"name": "Chicken Corn Soup", "price": 139}
],

"chicken_starters": [

{"name": "Chicken 65", "price":289},
{"name": "Chicken Lollipop", "price": 289},
{"name": "Drums of Heaven", "price": 289},
{"name": "Chicken Manchurian", "price": 289},
{"name": "Chicken Majestic", "price": 299},
{"name": "Pepper Chicken", "price": 299},
{"name": "Chicken 555", "price": 299},
{"name": "Spicy Fried Chicken", "price": 299},
{"name": "Chilli Chicken", "price": 269},
{"name": "Dragon Chicken", "price": 299},
{"name": "Hakka Chilli Chicken", "price": 299}


],

"egg_starters": [

{"name": "Chilli Egg", "price": 179},
{"name": "Egg 65", "price": 179},
{"name": "Egg Manchurian", "price": 189}


],

"nonveg_tikka": [

{"name": "Tandoori Chicken Half", "price": 319},
{"name": "Tandoori Chicken Full", "price": 579},
{"name": "Chicken Tikka", "price": 389}


],

"sea_food": [


{"name": "Chilli Fish", "price": 329},
{"name": "Apollo Fish", "price": 329},
{"name": "Fish Finger", "price": 329},
{"name": "Butter Garlic Prawns", "price": 349},
{"name": "Fried Prawns", "price": 349},
{"name": "Chilli Prawns", "price": 349},
{"name": "Golden Fried Prawns", "price": 349},
{"name": "Salt & Pepper Prawns", "price": 349}


],

"chicken_curries": [


{"name": "Chicken Tari Wala", "price": 299},
{"name": "Rara Chicken", "price": 299},
{"name": "Kadai Chicken", "price": 329},
{"name": "Punjabi Butter Chicken", "price": 329},
{"name": "Chicken Masala", "price": 299},
{"name": "Chicken Tikka Masala", "price": 329},
{"name": "Chicken Patyala", "price": 329},
{"name": "Chicken Roganjosh", "price": 299},
{"name": "Chicken Curry", "price": 299},
{"name": "Butter Chicken", "price": 329}


],

"egg_curries": [


{"name": "Egg Curry", "price": 159},
{"name": "Egg Bhurji", "price": 169}


],

"biryani": [


{"name": "Egg Biryani", "price": 219},
{"name": "Chicken Dum Biryani", "price": 289},
{"name": "Chicken Tikka Biryani", "price": 289},
{"name": "Chicken 65 Biryani", "price": 289},
{"name": "Chicken Fry Piece Biryani", "price": 289},
{"name": "Lollipop Biryani", "price": 299},
{"name": "Tandoori Biryani", "price": 299},
{"name": "Fish Biryani", "price": 299},
{"name": "Prawn Biryani", "price": 329},
{"name": "Special Chicken Biryani", "price": 369}


],

"nonveg_chinese": [


{"name": "Egg Noodles", "price": 179},
{"name": "Egg Schezwan Noodles", "price": 189},
{"name": "Chicken Noodles", "price": 189},
{"name": "Chicken Schezwan Noodles", "price": 209},
{"name": "Prawn Noodles", "price": 249},
{"name": "Mix Non Veg Noodles", "price": 299},
{"name": "Egg Fried Rice", "price": 179},
{"name": "Chicken Fried Rice", "price": 199},
{"name": "Chicken Schezwan Rice", "price": 209},
{"name": "Chicken Chilli Garlic Rice", "price": 199},
{"name": "Mixed Non Veg Fried Rice", "price": 299}


],

"nonveg_combos": [


{"name": "Chicken Fried Rice + Chicken Manchurian", "price": 329},
{"name": "Chicken Noodles + Chicken Manchurian", "price": 329}


],

"nonveg_rice": [


{"name": "Plain Rice", "price": 99},
{"name": "Jeera Rice", "price": 159},
{"name": "Green Peas Pulao", "price": 179},
{"name": "Curd Rice", "price": 179}


],

"nonveg_parathas": [

{"name": "Chicken Keema Paratha", "price": 179}

],
"rotis": [

{"name": "Plain Pulka", "price": 25},
{"name": "Butter Pulka", "price": 30},
{"name": "Plain Tandoori Roti", "price": 35},
{"name": "Butter Tandoori Roti", "price": 40},
{"name": "Plain Naan", "price": 45},
{"name": "Butter Naan", "price": 50},
{"name": "Plain Garlic Naan", "price": 55},
{"name": "Butter Garlic Naan", "price": 60}


],

"chopsuey": [


{"name": "Veg Chinese Chopsuey", "price": 259},
{"name": "Veg American Chopsuey", "price": 259},
{"name": "Veg Dragon Chopsuey", "price": 259},
{"name": "Chicken Chinese Chopsuey", "price": 299},
{"name": "Chicken American Chopsuey", "price": 299},
{"name": "Chicken Dragon Chopsuey", "price": 299}


],

"jumbo": [


{"name": "Chicken Family Pack", "price": 579},
{"name": "Chicken Biryani Jumbo Pack", "price": 1099},
{"name": "Veg Biryani Jumbo Pack", "price": 899}


],

"beverages": [

{"name": "Cool Drink 250ml", "price": 20},
{"name": "Sweet Lassi", "price": 69},
{"name": "Butter Milk", "price": 49},
{"name": "Water Bottle", "price": 20},
{"name": "Lemonade", "price": 59}


],

"papad": [

{"name": "Roasted Amritsari Papad", "price": 39},
{"name": "Masala Roasted Amritsari Papad", "price": 59}


]


}

# Server-side price lookup (name -> price). Used to validate/derive prices
# for every add-to-cart request so a client can never submit its own price.
restaurant_menu = {}
MENU_LOOKUP = {}
MENU_LOOKUP_ITEMS = {}
refresh_menu_globals()

start_settlement_poller()



@app.route("/")
def home():
    return render_template("home.html")


@app.route("/dinein")
def dinein():
    return render_template("dinein.html")


@app.route("/dinein-start", methods=["POST"])
def dinein_start():
    table = (request.form.get("table") or "").strip()
    name = (request.form.get("name") or "").strip()
    phone = (request.form.get("phone") or "").strip()

    if not table or not name or not phone:
        return render_template(
            "dinein.html",
            error="Please fill in table number, name and phone to continue.",
            table=table, name=name, phone=phone
        )

    table_id = get_or_create_table_id(table)
    save_table_customer_info(table_id, name, phone)

    return redirect(f"/menu?table={table}")


@app.route("/customerinfo")
def customerinfo():
    table = request.args.get("table", "")
    next_url = request.args.get("next", "/menu")
    return render_template("customerinfo.html", table=table, next_url=next_url)


@app.route("/customerinfo", methods=["POST"])
def customerinfo_submit():
    table = (request.form.get("table") or "").strip()
    name = (request.form.get("name") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    next_url = request.form.get("next") or f"/menu?table={table}"

    if not table or not name or not phone:
        return render_template(
            "customerinfo.html",
            table=table, next_url=next_url,
            error="Please fill in your name and phone to continue."
        )

    table_id = get_or_create_table_id(table)
    save_table_customer_info(table_id, name, phone)

    return redirect(next_url)


@app.route("/menu")
def menu():
    table = resolve_table_value()

    if table:
        get_or_create_table_id(table)

    return render_template(
        "menu.html",
        table=table,
        nav_active="menu"
    )


@app.route("/items")
def items():
    table = request.args.get("table")
    category = request.args.get("category")

    if category not in restaurant_menu:
        abort(404, description="Unknown menu category")

    return render_template(
        "items.html",
        table=table,
        category=category,
        items=restaurant_menu[category],
        nav_active="menu"
    )


@app.route("/itemdetails")
def itemdetails():
    name = request.args.get("name")

    item_data = MENU_LOOKUP_ITEMS.get(name)

    table = request.args.get("table")

    if item_data is None:
        abort(404, description="Unknown item")

    return render_template(
        "item_details.html",
        item=item_data,
        table=table,
        nav_active="menu"
    )


@app.route("/addtocart", methods=["POST"])
def addtocart():
    table = request.form.get("table")
    item_name = request.form.get("item_name")
    instructions = request.form.get("instructions")

    if item_name not in MENU_LOOKUP:
        abort(400, description="Unknown item")

    # Price is always looked up server-side from the menu — never trust the
    # client-submitted price, otherwise a crafted request could set any price.
    price = MENU_LOOKUP[item_name]

    try:
        quantity = int(request.form.get("quantity", ""))
    except (TypeError, ValueError):
        abort(400, description="Invalid quantity")

    if quantity <= 0:
        abort(400, description="Quantity must be positive")

    table_id = get_or_create_table_id(table)

    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO table_cart_items (table_id, item_name, unit_price, quantity, instructions)
            VALUES (?, ?, ?, ?, ?)
            """,
            (table_id, item_name, price, quantity, instructions)
        )
        conn.commit()

    table_cart = get_table_cart_items(table_id)
    grand_total = 0

    for item in table_cart:
        grand_total += item["price"] * item["quantity"]

    return render_template(
        "cart.html",
        cart=table_cart,
        grand_total=grand_total,
        table=table,
        nav_active="cart"
    )


@app.route("/cart")
def showcart():
    table = resolve_table_value()

    table_cart = []

    if table:
        table_id = get_or_create_table_id(table)
        table_cart = get_table_cart_items(table_id)

    grand_total = 0

    for item in table_cart:
        grand_total += item["price"] * item["quantity"]

    return render_template(
        "cart.html",
        cart=table_cart,
        grand_total=grand_total,
        table=table,
        nav_active="cart"
    )


@app.route("/deleteitem", methods=["POST"])
def deleteitem():
    item_name = request.form.get("item_name")
    table = resolve_table_value()

    table_cart = []

    if table:
        table_id = get_or_create_table_id(table)

        with get_db_connection() as conn:
            conn.execute(
                """
                DELETE FROM table_cart_items
                WHERE id = (
                    SELECT id
                    FROM table_cart_items
                    WHERE table_id = ? AND item_name = ?
                    ORDER BY id ASC
                    LIMIT 1
                )
                """,
                (table_id, item_name)
            )
            conn.commit()

        table_cart = get_table_cart_items(table_id)

    grand_total = 0

    for item in table_cart:
        grand_total += item["price"] * item["quantity"]

    return render_template(
        "cart.html",
        cart=table_cart,
        grand_total=grand_total,
        table=table,
        nav_active="cart"
    )


@app.route("/updatecartqty", methods=["POST"])
def updatecartqty():
    table = resolve_table_value()
    item_id = request.form.get("item_id")
    action = request.form.get("action")

    table_cart = []

    if table and item_id and action in ("inc", "dec"):
        table_id = get_or_create_table_id(table)

        with get_db_connection() as conn:
            if action == "inc":
                conn.execute(
                    """
                    UPDATE table_cart_items
                    SET quantity = quantity + 1
                    WHERE id = ? AND table_id = ?
                    """,
                    (item_id, table_id)
                )
            else:
                conn.execute(
                    """
                    UPDATE table_cart_items
                    SET quantity = quantity - 1
                    WHERE id = ? AND table_id = ? AND quantity > 1
                    """,
                    (item_id, table_id)
                )

            conn.commit()

        table_cart = get_table_cart_items(table_id)

    grand_total = 0

    for item in table_cart:
        grand_total += item["price"] * item["quantity"]

    return render_template(
        "cart.html",
        cart=table_cart,
        grand_total=grand_total,
        table=table,
        nav_active="cart"
    )


def build_petpooja_order_payload(table, customer_info, kot_type, kot_number, table_cart, total):
    """
    Builds the Save Order payload sent to PetPooja.
    PLACEHOLDER shape — correct field names once real PetPooja docs are available
    (see PETPOOJA_SETUP.md). petpooja_client.push_order() merges this with auth fields.
    """
    is_takeaway = table.upper().startswith("TK")
    gst = round(total * 0.05, 2)

    return {
        "OrderInfo": {
            "Customer": {
                "name": customer_info["name"],
                "phone": customer_info["phone"],
            },
            "OrderType": "Takeaway" if is_takeaway else "Dine In",
            "TableNo": table,
            "LocalOrderId": f"KOT{kot_number}",
            "OrderItem": [
                {
                    "name": item["name"],
                    "price": item["price"],
                    "quantity": item["quantity"],
                    "special_instructions": item.get("instructions") or "",
                }
                for item in table_cart
            ],
            "Tax": [{"name": "GST", "amount": gst}],
            "total": round(total + gst, 2),
        }
    }


def push_kot_to_petpooja(kot_id, order_payload):
    """
    Fire-and-record call to PetPooja after the local KOT is already committed.
    Never raises — customer flow must not break if PetPooja is unreachable;
    push_status/push_error are stored so staff can be alerted instead.
    """
    if not petpooja_client.is_configured():
        push_status, petpooja_order_id, push_error = "PENDING", None, "PetPooja credentials not configured yet"
    else:
        try:
            response = petpooja_client.push_order(order_payload)
            petpooja_order_id = str(response.get("order_id", ""))  # PLACEHOLDER field name
            push_status, push_error = "SENT", None
        except PetPoojaError as exc:
            push_status, petpooja_order_id, push_error = "FAILED", None, str(exc)

    with get_db_connection() as conn:
        conn.execute(
            "UPDATE kots SET petpooja_order_id = ?, push_status = ?, push_error = ? WHERE id = ?",
            (petpooja_order_id, push_status, push_error, kot_id)
        )
        conn.commit()

    return push_status


@app.route("/placeorder", methods=["POST"])
def placeorder():
    table = resolve_table_value()

    if not table:
        return redirect("/menu")

    table_id = get_or_create_table_id(table)

    customer_info = get_table_customer_info(table_id)
    if not customer_info:
        return redirect(f"/customerinfo?table={table}&next=/cart%3Ftable%3D{table}")

    table_cart = get_table_cart_items(table_id)

    if not table_cart:
        return redirect(f"/cart?table={table}")

    total = 0

    for item in table_cart:
        total += item["price"] * item["quantity"]

    with get_db_connection() as conn:
        unpaid_count_row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM kots
            WHERE table_id = ? AND payment_status = 'UNPAID'
            """,
            (table_id,)
        ).fetchone()

        unpaid_count = unpaid_count_row["count"]
        kot_type = "NEW TABLE" if unpaid_count == 0 else "RUNNING TABLE"

        next_kot_row = conn.execute(
            "SELECT COALESCE(MAX(kot_number), 100) + 1 AS next_kot FROM kots"
        ).fetchone()
        next_kot_number = next_kot_row["next_kot"]

        kot_cursor = conn.execute(
            """
            INSERT INTO kots (kot_number, table_id, kot_type, payment_status)
            VALUES (?, ?, ?, 'UNPAID')
            """,
            (next_kot_number, table_id, kot_type)
        )
        kot_id = kot_cursor.lastrowid

        conn.executemany(
            """
            INSERT INTO kot_items (kot_id, item_name, unit_price, quantity, instructions)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    kot_id,
                    item["name"],
                    item["price"],
                    item["quantity"],
                    item["instructions"]
                )
                for item in table_cart
            ]
        )

        conn.execute(
            """
            UPDATE tables
            SET
                status = 'OCCUPIED',
                occupied_since = COALESCE(occupied_since, CURRENT_TIMESTAMP),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (table_id,)
        )

        conn.execute(
            "DELETE FROM table_cart_items WHERE table_id = ?",
            (table_id,)
        )

        table_orders_rows = conn.execute(
            """
            SELECT
                k.kot_number AS order_id,
                COALESCE(SUM(ki.unit_price * ki.quantity), 0) AS total
            FROM kots k
            LEFT JOIN kot_items ki ON ki.kot_id = k.id
            WHERE k.table_id = ? AND k.payment_status = 'UNPAID'
            GROUP BY k.id, k.kot_number
            ORDER BY k.id ASC
            """,
            (table_id,)
        ).fetchall()

        conn.commit()

    table_orders = [dict(row) for row in table_orders_rows]

    table_food_total = 0

    for order in table_orders:
        table_food_total += order["total"]

    table_gst = round(table_food_total * 0.05, 2)
    table_total_with_gst = round(table_food_total + table_gst, 2)

    order_payload = build_petpooja_order_payload(
        table, customer_info, kot_type, next_kot_number, table_cart, total
    )
    push_status = push_kot_to_petpooja(kot_id, order_payload)

    return render_template(
        "order_success.html",
        order_id=next_kot_number,
        table=table,
        total=total,
        table_orders=table_orders,
        table_food_total=table_food_total,
        table_gst=table_gst,
        table_total_with_gst=table_total_with_gst,
        push_status=push_status,
        nav_active="orders"
    )


@app.route("/orders")
def orders():
    table = resolve_table_value()

    if not table:
        return redirect("/menu")

    table_id = get_or_create_table_id(table)
    order_history = get_table_order_history(table_id)

    return render_template(
        "orders.html",
        table=table,
        orders=order_history,
        order_count=len(order_history),
        nav_active="orders"
    )


@app.route("/bill")
def bill():
    table = resolve_table_value()

    if not table:
        return redirect("/menu")

    table_id = get_or_create_table_id(table)
    bill_data = get_table_bill_summary(table_id)

    return render_template(
        "bill.html",
        table=table,
        orders=bill_data["orders"],
        food_total=bill_data["food_total"],
        gst=bill_data["gst"],
        grand_total=bill_data["grand_total"],
        rounded_total=bill_data["rounded_total"],
        nav_active="bill"
    )


@app.route("/veg")
def veg():

    table = request.args.get("table")

    return render_template(
        "veg.html",
        table=table
    )


@app.route("/nonveg")
def nonveg():

    table = request.args.get("table")

    return render_template(
        "nonveg.html",
        table=table
    )

@app.route("/takeaway")
def takeaway():
    return render_template("takeaway.html")


@app.route("/takeaway-start", methods=["POST"])
def takeaway_start():
    name = (request.form.get("name") or "").strip()
    phone = (request.form.get("phone") or "").strip()

    if not name or not phone:
        return render_template(
            "takeaway.html",
            error="Please fill in your name and phone to continue.",
            name=name, phone=phone
        )

    # Persisted, atomic counter in SQLite instead of an in-memory global —
    # avoids duplicate tokens under concurrent requests or after a restart.
    with get_db_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT value FROM counters WHERE name = 'takeaway_token'"
        ).fetchone()
        next_value = row["value"] + 1
        conn.execute(
            "UPDATE counters SET value = ? WHERE name = 'takeaway_token'",
            (next_value,)
        )
        conn.commit()

    token = f"TK{next_value:03d}"
    table_id = get_or_create_table_id(token)
    save_table_customer_info(table_id, name, phone)

    return redirect(f"/menu?table={token}")


@app.route("/admin/poll-settlements")
@require_admin_token
def admin_poll_settlements():
    """
    Manually triggers one settlement-poll cycle immediately, instead of
    waiting for the background thread's interval. Useful for testing.
    """
    poll_petpooja_settlements()
    return jsonify({"status": "ok", "message": "Poll cycle executed. Check server logs for details."})


@app.route("/admin/sync-menu")
@require_admin_token
def admin_sync_menu():
    """
    Manually triggers a PetPooja menu pull and rebuilds the live menu.
    """
    if not petpooja_client.is_configured():
        return jsonify({
            "status": "not_configured",
            "message": (
                "Set PETPOOJA_APP_KEY, PETPOOJA_APP_SECRET, PETPOOJA_ACCESS_TOKEN "
                "and PETPOOJA_REST_ID as environment variables, then retry."
            )
        }), 400

    try:
        normalized_items, raw_categories_seen = sync_menu_from_petpooja()
    except PetPoojaError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 502

    refresh_menu_globals()

    category_map = load_category_map()
    unmapped_ids = {cat_id for cat_id, _ in raw_categories_seen} - {
        str(pid) for ids in category_map.values() for pid in ids
    }

    return jsonify({
        "status": "ok",
        "items_synced": len(normalized_items),
        "raw_categories_seen": [
            {"category_id": cid, "category_name": cname} for cid, cname in raw_categories_seen
        ],
        "unmapped_category_ids": sorted(unmapped_ids),
        "note": (
            "Add any unmapped_category_ids to category_map.json under the matching "
            "our_category_key, then call /admin/sync-menu again to pick them up."
        )
    })



if __name__ == "__main__":
    app.run(debug=app.debug)
