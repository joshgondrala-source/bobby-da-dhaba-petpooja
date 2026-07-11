# System Architecture & Data Flow

## 📊 Complete System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    RESTAURANT MANAGEMENT SYSTEM                 │
└─────────────────────────────────────────────────────────────────┘

┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│   CUSTOMER PAGE  │      │  MANAGER PAGE    │      │  OWNER DASHBOARD │
│  /menu?table=X  │      │    /manager      │      │      /owner      │
│  /cart?table=X  │      │                  │      │                  │
├──────────────────┤      ├──────────────────┤      ├──────────────────┤
│ Real-time        │      │ Real-time        │      │ Real-time        │
│ Refresh: 5s      │      │ Refresh: 8s      │      │ Refresh: 30s     │
│                  │      │                  │      │                  │
│ Shows:           │      │ Shows:           │      │ Shows:           │
│ - Menu items     │      │ - Bill requests  │      │ - Today's sales  │
│ - Cart items     │      │ - Unpaid orders  │      │ - GST collected  │
│ - Bill total     │      │ - Discount input │      │ - Revenue total  │
│                  │      │ - Payment button │      │ - Bills list     │
└──────────────────┘      └──────────────────┘      └──────────────────┘
         │                         │                        │
         │                         │                        │
         └─────────────────────────┴────────────────────────┘
                          │
                          ▼
              ┌────────────────────────┐
              │   FLASK BACKEND        │
              │      (app.py)          │
              ├────────────────────────┤
              │ Routes:                │
              │ /owner                 │
              │ /manager               │
              │ /cart                  │
              │ /placeorder            │
              │ /requestbill           │
              │ /generatebill          │
              │ /markpaid (CRITICAL)   │
              └────────────────────────┘
                          │
                          ▼
              ┌────────────────────────┐
              │   SQLite Database      │
              │   (restaurant.db)      │
              ├────────────────────────┤
              │ Tables:                │
              │ - tables               │
              │ - kots                 │
              │ - kot_items            │
              │ - bill_requests        │
              │ - table_cart_items     │
              └────────────────────────┘
```

---

## 🔄 Bill Finalization Flow (Most Important!)

```
STEP 1: CUSTOMER ORDERS
├─ Navigate to /menu?table=1
├─ Select items
├─ Add to cart (cart.html auto-refreshes every 5s)
├─ Place order
│  └─ Creates KOT with payment_status = 'UNPAID' ✗
└─ Request bill
   └─ Creates bill_request with is_active = 1

STEP 2: MANAGER PROCESSES (manager.html auto-refreshes every 8s)
├─ Sees "Table 1" in bill requests
├─ Generates final bill
│  └─ Shows:
│     - Food Total: ₹500
│     - GST (5%): ₹25
│     - Final Bill: ₹525
└─ Clicks "Payment Received" BUTTON
   └─ This is CRITICAL! ⭐
      - Updates kots.payment_status = 'PAID' ✓
      - Updates tables.status = 'AVAILABLE'
      - Clears bill_requests

STEP 3: OWNER DASHBOARD UPDATES (every 30s)
├─ Queries: SELECT * FROM kots WHERE payment_status='PAID'
├─ Calculates:
│  - Total Food: ₹500
│  - Total GST: ₹25
│  - Total Revenue: ₹525
└─ Displays in dashboard ✓
```

---

## 🎯 Real-Time Update Mechanism

### Cart Refresh (Every 5 Seconds)
```
Browser Script (cart.html)
│
├─ Fetch /cart?table=1
│
├─ Compare:
│  OLD: 2 items, ₹300
│  NEW: 3 items, ₹450
│
├─ If Different:
│  └─ Update DOM elements
│     - Cart list
│     - Item count
│     - Bill total
│     - Re-apply emojis
│
└─ If Same:
   └─ Silent check (no update)
```

### Manager Refresh (Every 8 Seconds)
```
Browser Script (manager.html)
│
├─ Fetch /manager
│
├─ Compare:
│  OLD: 3 bill requests
│  NEW: 4 bill requests
│
├─ If Different:
│  └─ location.reload()
│
└─ If Same:
   └─ Silent check (no update)
```

### Owner Refresh (Every 30 Seconds)
```
Browser Script (owner.html)
│
├─ Fetch /owner
│
├─ Compare:
│  OLD: ₹5000 total revenue
│  NEW: ₹5525 total revenue
│
├─ If Different:
│  └─ location.reload()
│
└─ If Same:
   └─ Silent check (no update)
```

---

## 💾 Database Changes During Bill Flow

```
INITIAL STATE:
┌─────────────────────────────────────┐
│ kots table                          │
├─────────────────────────────────────┤
│ id | table_id | payment_status      │
│ 1  | 1        | UNPAID       ✗      │
│ 2  | 2        | UNPAID       ✗      │
└─────────────────────────────────────┘

AFTER "Payment Received" CLICKED:
┌─────────────────────────────────────┐
│ kots table                          │
├─────────────────────────────────────┤
│ id | table_id | payment_status      │
│ 1  | 1        | PAID         ✓      │ ← Owner sees this!
│ 2  | 2        | UNPAID       ✗      │
└─────────────────────────────────────┘

OWNER DASHBOARD QUERY:
SELECT * FROM kots 
WHERE payment_status = 'PAID' 
AND DATE(created_at) = TODAY()

RESULT: Shows only row 1 ✓
```

---

## 🧮 GST Calculation Throughout System

```
STAGE 1: Customer Orders
├─ Item A: ₹100
├─ Item B: ₹200
└─ Subtotal: ₹300
   └─ NO GST yet (stored as-is in kot_items)

STAGE 2: Manager Generates Bill (final_bill.html)
├─ Food Total: ₹300
├─ GST (5%): ₹300 × 0.05 = ₹15
├─ Discount: 0%
└─ Final Bill: ₹315
   └─ Manager clicks "Payment Received"

STAGE 3: Owner Dashboard (owner.html)
├─ Queries PAID bills
├─ For each bill:
│  ├─ Food Total: ₹300
│  ├─ GST: ₹15
│  └─ Bill Total: ₹315
├─ Aggregates:
│  ├─ Total Food: ₹300
│  ├─ Total GST: ₹15
│  └─ Total Revenue: ₹315
└─ Displays in dashboard ✓
```

---

## 🚀 Simultaneous Operations Example

```
TIME: 12:00 PM

CUSTOMER TABLE 1          CUSTOMER TABLE 2         MANAGER              OWNER
├─ Add item ₹200    └─ Add item ₹300 (SILENT)    ├─ Views            ├─ Views
├─ Cart updates        (synced via polling)      │  dashboard         │  sales
│  after 5s                                       │  (checks every 8s)  │  (checks
├─ Place order ✓       └─ Place order ✓          │                     │   every 30s)
│  (creates KOT)         (creates KOT)           │                     │
│                                                 │                     │
TIME: 12:02 PM                                    │                     │
├─ Request bill    └─ Request bill              │                     │
│  (is_active=1)     (is_active=1)              └─ Sees 2 bills      └─ Still
│                                                 │  (auto-refresh      │  shows
TIME: 12:03 PM                                    │   triggers)         │  ₹0
├─ (waiting)       └─ (waiting)                 │                     │
│                                                 ├─ Generates bill    │
TIME: 12:04 PM                                    │  for Table 1        │
└─ (waiting)       └─ (waiting)                 │  ✓                  │
                                                 ├─ Clicks             │
TIME: 12:05 PM                                    │  "Payment Rec."     │
(nothing change)  └─ (nothing change)           │  for Table 1        └─ Auto-
                                                 │  (payment_status    │  refresh
TIME: 12:06 PM                                    │   = 'PAID')         │  after
└─ Mgr generates   └─ (waiting)                 │  ✓                  │  30s
   bill for Tbl 1                                │                     │
  (shows ₹210)      ├─ Mgr generates            └─ Still shows        ├─ Now
                    │  bill for Tbl 2              Table 2             │  shows
TIME: 12:07 PM      │  (shows ₹315)               (not paid yet)      │  ₹210
├─ Clicks            │                                                 │  (Table 1
│  "Payment Rec."    │                                                 │  paid)
│  for Tbl 1         │                                                 │
│  (PAID ✓)          └─ Clicks                                         │
│                       "Payment Rec."                                 │
TIME: 12:08 PM           for Tbl 2                                     │
└─ (waiting)            (PAID ✓)                                       └─ Final
                                                                           update
                                                                           shows:
                                                                           ₹525
                                                                           (both)
```

---

## 📈 Data Flow Summary

```
CUSTOMER DATA FLOW:
Menu → Items Added → Cart (updates every 5s) → Place Order → Request Bill
                        ↓
                    (real-time sync)

MANAGER DATA FLOW:
Bill Requests → Generate Bill → "Payment Received" → Database Update (PAID)
     ↑                                                       ↓
  (checks every 8s)                              (updates payment_status)

OWNER DATA FLOW:
Daily Sales Dashboard ← Queries PAID orders only
   (checks every 30s)     (from today)
                             ↓
                     (calculates GST)
                             ↓
                     (aggregates totals)
```

---

## 🔐 Data Isolation (Multiple Tables)

```
TABLE 1 DATA:
├─ cart: 2 items, ₹200
├─ orders: 2 KOTs
└─ bills: 1 PAID

TABLE 2 DATA:
├─ cart: 3 items, ₹300
├─ orders: 2 KOTs
└─ bills: 0 PAID (waiting)

TABLE 3 DATA:
├─ cart: 1 item, ₹100
├─ orders: 1 KOT
└─ bills: 0 PAID (waiting)

OWNER SEES: Only Table 1's bill (₹210 total)
MANAGER SEES: All tables' pending bills
EACH CUSTOMER: Only their own cart
```

---

## ✅ Verification Points

```
CART REFRESH: ✓
├─ 5-second interval active
├─ Updates when items change
└─ Multiple tables independent

MANAGER REFRESH: ✓
├─ 8-second interval active
├─ Detects new bill requests
└─ Auto-reload on changes

OWNER REFRESH: ✓
├─ 30-second interval active
├─ Shows PAID bills only
└─ Auto-reload on changes

BILLING ACCURACY: ✓
├─ GST = Food × 0.05
├─ Total = Food + GST
└─ Owner aggregates correctly

NO DATA MIXING: ✓
├─ Each table isolated
├─ No cross-contamination
└─ Revenue aggregates correctly
```

---

## 🎯 You're Ready!

All components working together:
1. ✅ Real-time updates at multiple intervals
2. ✅ GST calculated automatically
3. ✅ Bills finalized on demand
4. ✅ Owner dashboard tracks sales
5. ✅ Simultaneous operations work
6. ✅ Data integrity maintained

**Start testing and monitor your sales in real-time!** 🚀
