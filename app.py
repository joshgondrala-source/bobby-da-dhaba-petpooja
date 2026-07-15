from flask import Flask, render_template, request, session, redirect, abort
from datetime import datetime
import os
import sqlite3
from urllib.parse import parse_qs, urlparse

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
DB_PATH = os.path.join(app.root_path, "restaurant.db")


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

            CREATE TABLE IF NOT EXISTS bill_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_id INTEGER NOT NULL,
                requested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
                FOREIGN KEY (table_id) REFERENCES tables(id)
            );

            CREATE TABLE IF NOT EXISTS bills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_id INTEGER NOT NULL,
                food_total REAL NOT NULL,
                gst REAL NOT NULL,
                discount_percent REAL NOT NULL DEFAULT 0,
                discount_amount REAL NOT NULL DEFAULT 0,
                final_total REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'PAID')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                paid_at TEXT,
                FOREIGN KEY (table_id) REFERENCES tables(id)
            );

            CREATE TABLE IF NOT EXISTS counters (
                name TEXT PRIMARY KEY,
                value INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO counters (name, value) VALUES ('takeaway_token', 0)"
        )
        conn.commit()


init_db()


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


def get_table_order_history(table_id):
    with get_db_connection() as conn:
        kot_rows = conn.execute(
            """
            SELECT
                k.id,
                k.kot_number,
                k.kot_type,
                k.payment_status,
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
            GROUP BY k.id, k.kot_number, k.kot_type, k.payment_status, k.created_at
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
                "order_type": kot["kot_type"],
                "payment_status": kot["payment_status"],
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
                k.kot_type,
                k.created_at,
                COALESCE(SUM(ki.unit_price * ki.quantity), 0) AS total
            FROM kots k
            LEFT JOIN kot_items ki ON ki.kot_id = k.id
            WHERE k.table_id = ? AND k.payment_status = 'UNPAID'
            GROUP BY k.id, k.kot_number, k.kot_type, k.created_at
            ORDER BY k.id ASC
            """,
            (table_id,)
        ).fetchall()

        bill_request_row = conn.execute(
            """
            SELECT requested_at
            FROM bill_requests
            WHERE table_id = ? AND is_active = 1
            ORDER BY id DESC
            LIMIT 1
            """,
            (table_id,)
        ).fetchone()

    orders = [
        {
            "order_id": row["kot_number"],
            "order_type": row["kot_type"],
            "time": format_table_timestamp(row["created_at"]),
            "total": float(row["total"])
        }
        for row in unpaid_rows
    ]

    food_total = sum(order["total"] for order in orders)
    gst = round(food_total * 0.05, 2)
    grand_total = round(food_total + gst, 2)

    return {
        "orders": orders,
        "food_total": food_total,
        "gst": gst,
        "grand_total": grand_total,
        "bill_requested": bill_request_row is not None,
        "requested_at": format_table_timestamp(bill_request_row["requested_at"]) if bill_request_row else None,
    }

# MENU DATA
restaurant_menu = {
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


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/dinein")
def dinein():
    return render_template("dinein.html")


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


@app.route("/placeorder", methods=["POST"])
def placeorder():
    table = resolve_table_value()

    if not table:
        return redirect("/menu")

    table_id = get_or_create_table_id(table)
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

    return render_template(
        "order_success.html",
        order_id=next_kot_number,
        table=table,
        total=total,
        table_orders=table_orders,
        table_food_total=table_food_total,
        table_gst=table_gst,
        table_total_with_gst=table_total_with_gst,
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
        bill_requested=bill_data["bill_requested"],
        requested_at=bill_data["requested_at"],
        nav_active="bill"
    )


@app.route("/kitchen")
def kitchen():
    with get_db_connection() as conn:
        kot_rows = conn.execute(
            """
            SELECT
                k.id,
                k.kot_number,
                k.kot_type,
                k.created_at,
                t.table_number
            FROM kots k
            INNER JOIN tables t ON t.id = k.table_id
            WHERE k.payment_status = 'UNPAID'
            ORDER BY k.id DESC
            """
        ).fetchall()

        kitchen_orders = []

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

            time_value = kot["created_at"]
            try:
                time_value = datetime.strptime(kot["created_at"], "%Y-%m-%d %H:%M:%S").strftime("%I:%M %p")
            except (ValueError, TypeError):
                pass

            kitchen_orders.append({
                "order_id": kot["kot_number"],
                "status": kot["kot_type"],
                "time": time_value,
                "table": str(kot["table_number"]),
                "items": [
                    {
                        "name": item["item_name"],
                        "quantity": item["quantity"],
                        "instructions": item["instructions"]
                    }
                    for item in item_rows
                ]
            })

    return render_template(
        "kitchen.html",
        orders=kitchen_orders
    )
@app.route("/requestbill", methods=["POST"])
def requestbill():
    table = resolve_table_value()

    if not table:
        return redirect("/menu")

    table_id = get_or_create_table_id(table)

    with get_db_connection() as conn:
        existing = conn.execute(
            """
            SELECT id
            FROM bill_requests
            WHERE table_id = ? AND is_active = 1
            LIMIT 1
            """,
            (table_id,)
        ).fetchone()

        if not existing:
            conn.execute(
                "INSERT INTO bill_requests (table_id, is_active) VALUES (?, 1)",
                (table_id,)
            )
            conn.commit()

    return render_template(
        "bill_requested.html",
        table=table
    )
@app.route("/manager")
def manager():
    with get_db_connection() as conn:
        bill_request_rows = conn.execute(
            """
            SELECT t.table_number
            FROM bill_requests br
            INNER JOIN tables t ON t.id = br.table_id
            WHERE br.is_active = 1
            ORDER BY br.id ASC
            """
        ).fetchall()

        order_rows = conn.execute(
            """
            SELECT
                k.kot_number AS order_id,
                t.table_number,
                COALESCE(SUM(ki.unit_price * ki.quantity), 0) AS total
            FROM kots k
            INNER JOIN tables t ON t.id = k.table_id
            LEFT JOIN kot_items ki ON ki.kot_id = k.id
            WHERE k.payment_status = 'UNPAID'
            GROUP BY k.id, k.kot_number, t.table_number
            ORDER BY k.id ASC
            """
        ).fetchall()

    manager_bill_requests = [
        {"table": str(row["table_number"])}
        for row in bill_request_rows
    ]

    manager_orders = [
        {
            "order_id": row["order_id"],
            "table": str(row["table_number"]),
            "total": row["total"]
        }
        for row in order_rows
    ]

    return render_template(
        "manager.html",
        bill_requests=manager_bill_requests,
        orders=manager_orders
    )
@app.route("/generatebill", methods=["POST"])
def generatebill():

    table = request.form.get("table")

    if not table:
        return redirect("/manager")

    table_id = get_or_create_table_id(table)

    try:
        discount = float(request.form.get("discount", 0) or 0)
    except (TypeError, ValueError):
        discount = 0.0

    # Clamp to a sane 0-100% range regardless of what the client sends.
    discount = max(0.0, min(discount, 100.0))

    with get_db_connection() as conn:
        total_row = conn.execute(
            """
            SELECT COALESCE(SUM(ki.unit_price * ki.quantity), 0) AS food_total
            FROM kots k
            INNER JOIN kot_items ki ON ki.kot_id = k.id
            WHERE k.table_id = ? AND k.payment_status = 'UNPAID'
            """,
            (table_id,)
        ).fetchone()

        food_total = float(total_row["food_total"])
        gst = food_total * 0.05
        subtotal = food_total + gst
        discount_amount = subtotal * discount / 100
        final_total = subtotal - discount_amount
        rounded_total = round(final_total)

        # Replace any earlier pending bill for this table so /markpaid always
        # settles using the latest discount instead of losing it.
        conn.execute(
            "DELETE FROM bills WHERE table_id = ? AND status = 'PENDING'",
            (table_id,)
        )
        conn.execute(
            """
            INSERT INTO bills (table_id, food_total, gst, discount_percent, discount_amount, final_total, status)
            VALUES (?, ?, ?, ?, ?, ?, 'PENDING')
            """,
            (table_id, food_total, gst, discount, discount_amount, final_total)
        )
        conn.commit()

    return render_template(
        "final_bill.html",
        table=table,
        food_total=food_total,
        gst=gst,
        discount=discount,
        discount_amount=discount_amount,
        final_total=final_total,
        rounded_total=rounded_total
    )


@app.route("/markpaid", methods=["POST"])
def markpaid():
    table = resolve_table_value()

    if table:
        table_id = get_or_create_table_id(table)

        with get_db_connection() as conn:
            pending_bill = conn.execute(
                """
                SELECT id, food_total, gst, discount_percent, discount_amount, final_total
                FROM bills
                WHERE table_id = ? AND status = 'PENDING'
                ORDER BY id DESC
                LIMIT 1
                """,
                (table_id,)
            ).fetchone()

            if pending_bill:
                # Settle using the manager's already-generated (and possibly
                # discounted) bill instead of recomputing from scratch.
                conn.execute(
                    """
                    UPDATE bills
                    SET status = 'PAID', paid_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (pending_bill["id"],)
                )
            else:
                # Manager marked paid without generating a bill first — fall
                # back to the raw unpaid total with zero discount, but still
                # record it so owner reporting stays accurate.
                total_row = conn.execute(
                    """
                    SELECT COALESCE(SUM(ki.unit_price * ki.quantity), 0) AS food_total
                    FROM kots k
                    INNER JOIN kot_items ki ON ki.kot_id = k.id
                    WHERE k.table_id = ? AND k.payment_status = 'UNPAID'
                    """,
                    (table_id,)
                ).fetchone()

                food_total = float(total_row["food_total"])
                gst = food_total * 0.05
                final_total = food_total + gst

                conn.execute(
                    """
                    INSERT INTO bills (table_id, food_total, gst, discount_percent, discount_amount, final_total, status, paid_at)
                    VALUES (?, ?, ?, 0, 0, ?, 'PAID', CURRENT_TIMESTAMP)
                    """,
                    (table_id, food_total, gst, final_total)
                )

            conn.execute(
                """
                UPDATE kots
                SET payment_status = 'PAID'
                WHERE table_id = ? AND payment_status = 'UNPAID'
                """,
                (table_id,)
            )

            conn.execute(
                """
                UPDATE tables
                SET
                    status = 'AVAILABLE',
                    occupied_since = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (table_id,)
            )

            conn.execute(
                """
                UPDATE bill_requests
                SET is_active = 0
                WHERE table_id = ? AND is_active = 1
                """,
                (table_id,)
            )

            conn.execute(
                "DELETE FROM table_cart_items WHERE table_id = ?",
                (table_id,)
            )

            conn.commit()

    return redirect("/manager")


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

    return redirect(f"/menu?table={token}")


@app.route("/owner")
def owner():
    """Owner dashboard showing today's total sales with GST"""
    from datetime import datetime as dt

    # SQLite's CURRENT_TIMESTAMP is stored in UTC, so "today" must also be
    # computed in UTC — comparing it against the server's local date caused
    # bills to vanish from the dashboard once local time crossed midnight
    # ahead of UTC (e.g. evenings in IST, UTC+5:30).
    today = dt.utcnow().strftime("%Y-%m-%d")

    with get_db_connection() as conn:
        # Revenue is reported from the `bills` table (one row per settled
        # checkout) so any manager discount is correctly reflected — summing
        # raw kot_items would ignore discounts and overstate revenue.
        paid_bills = conn.execute(
            """
            SELECT
                b.id,
                t.table_number,
                b.food_total,
                b.gst,
                b.discount_percent,
                b.discount_amount,
                b.final_total,
                b.paid_at
            FROM bills b
            INNER JOIN tables t ON t.id = b.table_id
            WHERE b.status = 'PAID'
            AND DATE(b.paid_at) = ?
            ORDER BY b.paid_at DESC
            """,
            (today,)
        ).fetchall()

        # Calculate totals
        total_food = 0
        total_gst = 0
        total_revenue = 0

        finalized_bills = []

        for bill in paid_bills:
            food_total = float(bill["food_total"])
            gst = float(bill["gst"])
            grand_total = float(bill["final_total"])

            total_food += food_total
            total_gst += gst
            total_revenue += grand_total

            time_value = bill["paid_at"]
            try:
                time_value = dt.strptime(bill["paid_at"], "%Y-%m-%d %H:%M:%S").strftime("%I:%M %p")
            except (ValueError, TypeError):
                pass

            finalized_bills.append({
                "bill_id": bill["id"],
                "table": str(bill["table_number"]),
                "food_total": food_total,
                "gst": gst,
                "discount_percent": float(bill["discount_percent"]),
                "discount_amount": float(bill["discount_amount"]),
                "total": grand_total,
                "time": time_value
            })

    return render_template(
        "owner.html",
        total_food=total_food,
        total_gst=total_gst,
        total_revenue=total_revenue,
        finalized_bills=finalized_bills,
        bill_count=len(finalized_bills)
    )


if __name__ == "__main__":
    app.run(debug=True)