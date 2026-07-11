from flask import Flask, render_template, request
from flask import redirect
from datetime import datetime
import os
import sqlite3
from urllib.parse import parse_qs, urlparse

app = Flask(__name__)
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
            """
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
        table = current_table

    return (table or "").strip() or None


def get_table_cart_items(table_id):
    with get_db_connection() as conn:
        rows = conn.execute(
            """
            SELECT
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

current_table=None

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


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/dinein")
def dinein():
    return render_template("dinein.html")


@app.route("/menu")
def menu():
    global current_table

    table = resolve_table_value()

    if table:
        current_table = table
        get_or_create_table_id(table)

    return render_template(
        "menu.html",
        table=current_table
    )

@app.route("/items")
def items():

    table = request.args.get("table")
    category = request.args.get("category")

    return render_template(
        "items.html",
        table=table,
        category=category,
        items=restaurant_menu[category]
    )


@app.route("/itemdetails")
def itemdetails():

    name = request.args.get("name")

    item_data = None

    for category in restaurant_menu.values():

        for item in category:

            if item["name"] == name:
                item_data = item
                break

    table = request.args.get("table")

    return render_template(
     "item_details.html",
     item=item_data,
     table=table
)
    
@app.route("/addtocart", methods=["POST"])
def addtocart():
    table = request.form.get("table")
    item_name = request.form.get("item_name")
    price = int(request.form.get("price"))
    quantity = int(request.form.get("quantity"))
    instructions = request.form.get("instructions")

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
     table=table
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
        table=table
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
        table=table
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

    table_total = 0

    for order in table_orders:
        table_total += order["total"]

    return render_template(
        "order_success.html",
        order_id=next_kot_number,
        table=table,
        total=total,
        table_orders=table_orders,
        table_total=table_total
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
            ORDER BY k.id ASC
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

    discount = float(request.form.get("discount", 0) or 0)

    gst = food_total * 0.05

    subtotal = food_total + gst

    discount_amount = (
        subtotal * discount / 100
    )

    final_total = (
        subtotal - discount_amount
    )

    rounded_total = round(final_total)

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

takeaway_token = 1

@app.route("/takeaway")
def takeaway():

    global takeaway_token

    token = f"TK{takeaway_token:03d}"

    takeaway_token += 1

    return redirect(f"/menu?table={token}")


@app.route("/owner")
def owner():
    """Owner dashboard showing today's total sales with GST"""
    from datetime import date, datetime as dt
    
    today = date.today().strftime("%Y-%m-%d")
    
    with get_db_connection() as conn:
        # Get all paid orders from today
        paid_orders = conn.execute(
            """
            SELECT
                k.id,
                k.kot_number,
                t.table_number,
                k.created_at,
                COALESCE(SUM(ki.unit_price * ki.quantity), 0) AS food_total
            FROM kots k
            INNER JOIN tables t ON t.id = k.table_id
            LEFT JOIN kot_items ki ON ki.kot_id = k.id
            WHERE k.payment_status = 'PAID'
            AND DATE(k.created_at) = ?
            GROUP BY k.id, k.kot_number, t.table_number, k.created_at
            ORDER BY k.created_at DESC
            """,
            (today,)
        ).fetchall()
        
        # Calculate totals
        total_food = 0
        total_gst = 0
        total_revenue = 0
        
        finalized_bills = []
        
        for order in paid_orders:
            food_total = float(order["food_total"])
            gst = food_total * 0.05
            grand_total = food_total + gst
            
            total_food += food_total
            total_gst += gst
            total_revenue += grand_total
            
            time_value = order["created_at"]
            try:
                time_value = dt.strptime(order["created_at"], "%Y-%m-%d %H:%M:%S").strftime("%I:%M %p")
            except (ValueError, TypeError):
                pass
            
            finalized_bills.append({
                "kot_number": order["kot_number"],
                "table": str(order["table_number"]),
                "food_total": food_total,
                "gst": gst,
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