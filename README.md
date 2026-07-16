# 🍲 Bobby Da Dhaba — QR Ordering, pushed straight into PetPooja

A QR-based, **customer-only** ordering web app built for **Bobby Da Dhaba** (Madhapur), using
**Python, Flask, SQLite, HTML, CSS and JavaScript**.

Customers scan one shared QR code at the restaurant, choose Dine In or Takeaway, order from the
menu, and their order is **pushed directly into PetPooja** — the same POS the restaurant already
uses to print KOTs and bills. There is no kitchen/manager/owner dashboard in this app on purpose:
the restaurant runs on a single manager PC + one KOT/bill printer, so this app's only job is to
replace manual order entry, not to replace PetPooja.

This project is a purpose-built clone/evolution of an earlier, more general
[restaurant-ordering-system](https://github.com/joshgondrala-source/restaurant-ordering-system)
project, adapted specifically for this restaurant's real single-PC workflow and PetPooja
integration.

---

## 🚦 How it works

1. Customer scans the one QR code placed at the restaurant (table or counter) → opens the home page.
2. Chooses **Dine In** (enters table number) or **Takeaway** (gets a token like `TK001`).
3. Enters name + phone once per table/session (needed for PetPooja's order payload).
4. Browses the menu, adds items to a shared cart for that table.
5. Places the order → app builds a PetPooja Save Order payload and pushes it → PetPooja prints
   the KOT on the manager's existing printer, same as if the manager typed it in manually.
6. Customer can keep ordering, view past orders for the session, and see an estimated GST-inclusive
   bill — but the **actual bill/payment always happens at the counter**, exactly like today.
7. Once the manager settles the table in PetPooja (or cancels/voids an order because an item's
   unavailable and the customer left), a background poller detects this and **automatically clears
   the table** in our app — so the next customer at that table gets a clean slate.

No live "preparing/ready" status is tracked, because the restaurant has no kitchen display — just
one printer. Order status shown to the customer is intentionally simple: *sent to kitchen*,
*confirm with counter* (if the push failed), *cancelled*, or *paid*.

---

## 🛠 Tech stack

- **Backend**: Python, Flask, SQLite
- **Frontend**: Jinja2 templates, HTML/CSS/JS (mobile-first)
- **POS integration**: PetPooja Partner APIs (menu pull, order push, order status polling)
- **Deployment**: Render / Azure (gunicorn, single worker)

---

## 📂 Project structure

```
bobby-da-dhaba-petpooja/
├── app.py                  # Flask app: routes, DB schema/migrations, PetPooja wiring, poller
├── petpooja_client.py      # Thin HTTP client for PetPooja's Menu/Save Order/Status APIs
├── menu_sync.py            # Normalizes PetPooja's raw menu response into our UI's format
├── category_map.json       # Maps PetPooja category ids -> our existing UI category keys
├── generate_qr_card.py     # Generates one printable QR card image (points to the home page)
├── requirements.txt
├── Procfile                # gunicorn start command (pinned to 1 worker — see below)
├── .env.example            # Template for required environment variables
├── PETPOOJA_SETUP.md       # PetPooja integration setup, sync workflow, production checklist
├── restaurant.db           # SQLite database (tables, cart, KOTs, PetPooja item cache)
└── templates/               # All customer-facing pages (home, dinein, takeaway, menu, veg/nonveg,
                              # items, cart, orders, bill, order_success, customerinfo)
```

---

## ▶️ Running locally

```bash
python -m venv venv
venv\Scripts\activate            # (Windows)  |  source venv/bin/activate   (macOS/Linux)
pip install -r requirements.txt
python app.py
```

Visit `http://127.0.0.1:5000`. Without any `.env` file, the app runs fully functional against a
built-in fallback menu, and PetPooja push/poll calls safely no-op (nothing is configured yet).

## 🔑 Environment variables

Copy `.env.example` to `.env` and fill in real values before deploying. See `PETPOOJA_SETUP.md`
for the full PetPooja credential list and the production checklist (`SECRET_KEY`, `ADMIN_TOKEN`,
`FLASK_DEBUG=0`, single-worker gunicorn, etc.).

## 🧪 Testing

```bash
python test_menu_sync.py
```

Verifies the PetPooja menu normalize → category-map → build-menu pipeline against a sample
payload, without needing real credentials.

---

## 👨‍💻 Author

**G. Jyothi Swaroop**
Chemical Engineering Undergraduate, National Institute of Technology Warangal

📧 joshgondrala@gmail.com
🔗 [GitHub](https://github.com/joshgondrala-source) · [LinkedIn](https://www.linkedin.com/in/jyothi-swaroop-gondrala-2303373a6)
