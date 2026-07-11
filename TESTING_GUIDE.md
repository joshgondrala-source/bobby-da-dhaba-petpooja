# Testing Guide - Owner Dashboard & Real-Time Features

## Overview
This guide will help you verify that:
1. ✅ Owner dashboard shows today's total sales with GST
2. ✅ Bills are finalized only after manager clicks "Payment Received"
3. ✅ Cart refreshes in real-time (every 5 seconds)
4. ✅ Manager dashboard updates in real-time (every 8 seconds)
5. ✅ Simultaneous operations work correctly

---

## 🧪 Test Scenario 1: Cart Real-Time Refresh

**Objective**: Verify that the cart updates in real-time when items are added/removed

### Steps:
1. Open TWO browser windows/tabs side-by-side
2. **Tab 1**: Navigate to `/menu?table=1` and select a category (e.g., Veg)
3. **Tab 2**: Navigate to `/cart?table=1` (cart will be empty initially)
4. **Tab 1**: Add an item to cart (click an item → add to cart)
5. **Observe Tab 2**: Within 5 seconds, the item should appear in the cart WITHOUT manually refreshing
6. **Tab 1**: Add another item
7. **Observe Tab 2**: The new item should appear, and total should update
8. **Tab 2**: Delete an item manually
9. **Observe Tab 1**: Go back to cart in Tab 1, it should show the updated cart

### Expected Result:
- Tab 2 cart updates automatically every 5 seconds
- No manual page refresh needed
- Cart counts and totals update correctly
- Changes from Tab 1 appear in Tab 2 within 5 seconds

---

## 🧪 Test Scenario 2: Manager Dashboard Real-Time Updates

**Objective**: Verify that manager dashboard updates when new bill requests arrive

### Steps:
1. Open THREE browser windows/tabs:
   - **Tab 1**: `/menu?table=1` (Customer)
   - **Tab 2**: `/manager` (Manager)
   - **Tab 3**: `/kitchen` (Kitchen)
   
2. **Tab 1**: Add items to cart
3. **Tab 1**: Click "Place Order"
4. **Observe Tab 3**: Order appears in kitchen display
5. **Observe Tab 2**: Stay on manager page, within 8 seconds, no changes yet (orders not requested bill)
6. **Tab 1**: Navigate to `/requestbill?table=1`
7. **Observe Tab 2**: Within 8 seconds, "Table 1" should appear in bill requests WITHOUT manual refresh
8. **Tab 1**: Go back to cart, add more items
9. **Tab 1**: Place another order
10. **Observe Tab 2**: Orders count should update automatically

### Expected Result:
- Manager dashboard updates every 8 seconds
- New bill requests appear automatically
- No manual refresh needed
- Multiple simultaneous operations work

---

## 🧪 Test Scenario 3: Bill Finalization & Owner Dashboard

**Objective**: Verify that bills are ONLY counted in owner dashboard after payment is received

### Steps:
1. Open browser tabs for:
   - **Tab 1**: `/manager` (Manager)
   - **Tab 2**: `/owner` (Owner Dashboard)
   - **Tab 3**: `/menu?table=2` (Customer Table 2)

2. **Tab 3**: Add items and place order (amount = ₹500 for example)
3. **Tab 3**: Request bill
4. **Tab 1 (Manager)**: Generate final bill for Table 2
5. **Tab 1**: You'll see the final bill with:
   - Food Total: ₹500
   - GST (5%): ₹25
   - Total: ₹525
6. **Observe Tab 2 (Owner)**: Owner dashboard should STILL show 0 total sales (bill not paid yet)
7. **Tab 1**: Click "Payment Received" button
8. **Observe Tab 2 (Owner)**: Within 30 seconds, owner dashboard should update with:
   - Bills Finalized: 1
   - Food Total: ₹500
   - GST Collected: ₹25
   - Total Revenue: ₹525
   - The bill appears in "Finalized Bills" section

### Expected Result:
- Owner dashboard shows 0 until "Payment Received" is clicked
- Bill only appears in owner dashboard after payment is confirmed
- GST is correctly calculated (5% of food total)
- Multiple payments accumulate correctly

---

## 🧪 Test Scenario 4: Simultaneous Multiple Tables

**Objective**: Verify that simultaneous operations don't interfere with each other

### Steps:
1. Open 4 browser windows:
   - **Tab 1**: `/manager` (Manager)
   - **Tab 2**: `/owner` (Owner)
   - **Tab 3**: `/menu?table=T1` (Table T1 - Customer)
   - **Tab 4**: `/menu?table=T2` (Table T2 - Customer)

2. **Tab 3 & Tab 4**: Simultaneously add items to carts (same items, different quantities)
3. **Tab 3**: Place order with ₹300 total
4. **Tab 4**: Place order with ₹450 total
5. **Tab 3 & Tab 4**: Both request bills
6. **Observe Tab 1**: Both tables appear in bill requests
7. **Tab 1**: Generate bill for Table T1 (₹300)
8. **Tab 1**: Generate bill for Table T2 (₹450)
9. **Tab 1**: Click "Payment Received" for Table T1
10. **Observe Tab 2**: Owner dashboard shows:
    - Bills Finalized: 1
    - Total Revenue: ₹315 (300 + 5% GST)
11. **Tab 1**: Click "Payment Received" for Table T2
12. **Observe Tab 2**: Within 30 seconds, owner dashboard updates to:
    - Bills Finalized: 2
    - Total Revenue: ₹819.75 (315 + 472.5)

### Expected Result:
- Multiple tables can be processed simultaneously
- Each table's data is isolated and correct
- Owner dashboard accurately aggregates all payments
- No data corruption or mixing between tables
- GST is correctly calculated for each bill

---

## 🧪 Test Scenario 5: Auto-Refresh Intervals

**Objective**: Verify refresh intervals and consistency

### Steps:
1. **Tab 1**: Open `/cart?table=5` and observe console (F12 → Console)
2. Watch the console for ~30 seconds
3. You should see: "🔄 Cart updated in real-time" messages OR silent checks (no update needed)
4. **Tab 2**: Open `/manager` and observe console
5. Similar pattern - checks every 8 seconds
6. **Tab 3**: Open `/owner` and observe refresh indicator in header
7. The timestamp should update every minute
8. Manual "🔄 Refresh Now" button should reload immediately

### Expected Result:
- Cart refreshes every 5 seconds
- Manager dashboard checks every 8 seconds
- Owner dashboard auto-checks every 30 seconds
- Manual refresh buttons work immediately
- No errors in console

---

## 🧪 Test Scenario 6: GST Calculation Verification

**Objective**: Verify GST calculations across the system

### Test Cases:
1. Order Amount: ₹100 → GST: ₹5.00 → Total: ₹105
2. Order Amount: ₹999 → GST: ₹49.95 → Total: ₹1048.95
3. Order Amount: ₹500 → GST: ₹25.00 → Total: ₹525
4. Order Amount: ₹1 → GST: ₹0.05 → Total: ₹1.05

### Verification Points:
- Manager final bill page shows correct GST
- Owner dashboard aggregates correct GST amounts
- Bill list shows correct individual GST amounts

---

## 🐛 Troubleshooting

### Issue: Cart doesn't update automatically
- **Solution**: Check browser console (F12) for JavaScript errors
- **Check**: Is JavaScript enabled?
- **Check**: Are you on the `/cart` page?

### Issue: Manager dashboard doesn't show new requests
- **Solution**: Verify bill request was actually created
- **Check**: Go to `/requestbill?table=X` was called
- **Check**: Check browser console for errors

### Issue: Owner dashboard shows 0 sales
- **Solution**: Verify payment was actually marked
- **Check**: Go to manager, click "Payment Received" button
- **Check**: The `/markpaid` endpoint should update the database

### Issue: Numbers don't match
- **Solution**: Verify GST calculation: Food Total × 0.05
- **Check**: Calculate manually: ₹100 × 0.05 = ₹5.00
- **Check**: Is rounding correct?

---

## ✅ Verification Checklist

After testing all scenarios:

- [ ] Cart updates every 5 seconds without manual refresh
- [ ] Manager dashboard updates every 8 seconds without manual refresh
- [ ] Owner dashboard updates every 30 seconds
- [ ] Bills ONLY appear in owner dashboard AFTER "Payment Received" is clicked
- [ ] GST is correctly calculated at 5%
- [ ] Multiple simultaneous tables work without interference
- [ ] No JavaScript errors in console
- [ ] All timestamps display correctly
- [ ] Refresh buttons work immediately
- [ ] Data persists across page refreshes
- [ ] Multiple browser windows can view different tables simultaneously
- [ ] Bill totals match across manager and owner dashboards

---

## 📊 Expected User Flow

```
CUSTOMER FLOW:
Menu → Select Items → Add to Cart → Cart (real-time updates every 5s)
→ Place Order → Request Bill → Bill Requested Page

MANAGER FLOW:
Manager Dashboard (updates every 8s) → See new bill request
→ Generate Final Bill → Review Bill → Click "Payment Received"

OWNER FLOW:
Owner Dashboard (updates every 30s) → See finalized bills
→ GST breakdown shows correctly → Total revenue accumulates
```

---

## 🚀 Performance Notes

- Cart refresh: **5 seconds** - Quick updates for customer
- Manager refresh: **8 seconds** - Moderate for staff operations
- Owner refresh: **30 seconds** - Less frequent for analytics dashboard
- All refreshes use polling (no WebSocket) for compatibility
- Updates only trigger page reload if content changes (optimization)
