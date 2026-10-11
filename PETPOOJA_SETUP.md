# PetPooja Integration Setup

This is based on PetPooja's real **PetpoojaOnlineOrdering APIs V2.1.0** docs
(received Oct 2026), not guesses. The integration is **webhook-driven in both
directions**, not request/pull-based:

| Direction | What happens |
|---|---|
| Menu | PetPooja → us. PetPooja calls `POST /petpooja/push-menu` on our server whenever the restaurant's menu changes in their system. (The old pull-based "Fetch Menu" API is deprecated.) |
| Order push | Us → PetPooja. We call PetPooja's `Save Order` endpoint after a KOT is created locally. |
| Order status | PetPooja → us. We pass a `callback_url` (pointing at `POST /petpooja/callback`) in every Save Order request; PetPooja posts kitchen-status updates to it. There is **no polling/"get status" endpoint**. |
| Order cancel | Us → PetPooja. We call `Update Order Status` — the **only** status we're allowed to push is cancel (`status: "-1"`). |

## What's built
- `petpooja_client.py` — HTTP client for the real Save Order and Update
  Order Status endpoints (correct URLs/payload shapes from the V2.1.0 spec).
- `menu_sync.py` — normalizes the payload PetPooja pushes to
  `/petpooja/push-menu` into our app's internal menu format.
- `category_map.json` — maps PetPooja's raw `category_id`s to our existing
  UI category keys (`veg_soups`, `veg_starters`, etc.).
- `/petpooja/push-menu` — inbound webhook PetPooja calls on menu changes;
  caches items in the `petpooja_items` SQLite table.
- `/petpooja/callback` — inbound webhook PetPooja calls with order/kitchen
  status updates; matched back to our KOT via `client_order_id`.
- `/admin/menu-status` — read-only report of the last menu push received and
  which PetPooja category ids still need mapping.
- `/admin/settle-table` — manual fallback for staff to mark a table fully
  paid/cleared (see "Open question for PetPooja" below for why this exists).
- Until PetPooja pushes a menu, the app keeps using the original hardcoded
  menu (`FALLBACK_MENU` in `app.py`) — nothing breaks locally without
  credentials.

## ⚠️ Open question for PetPooja — ask before going live
PetPooja's documented callback only reports **kitchen progress**
(`-1 Cancelled, 1/2/3 Accepted, 4 Dispatched, 5 Food Ready, 10 Delivered`).
**There is no documented "bill paid/settled" status.** Until PetPooja's
integrations team confirms how (or whether) a payment/settlement signal can
reach a third-party app, staff must use `/admin/settle-table` to manually
free a table once they've taken payment at the counter in PetPooja directly.
Ask them directly: *"Once a manager settles a table's bill in PetPooja, is
there any webhook/field that tells our app the table is paid?"*

## Environment variables to set
```
PETPOOJA_APP_KEY=
PETPOOJA_APP_SECRET=
PETPOOJA_ACCESS_TOKEN=
PETPOOJA_REST_ID=
PETPOOJA_RES_NAME=
PETPOOJA_RES_ADDRESS=
PETPOOJA_RES_CONTACT=

# Public HTTPS URL of this app once deployed (Azure/Render) — required so
# the callback_url we send PetPooja is reachable from the internet.
PUBLIC_BASE_URL=https://your-app.azurewebsites.net

# Only set these once PetPooja shares production endpoint URLs; otherwise
# the client falls back to their documented dev/sandbox URLs.
# PETPOOJA_SAVE_ORDER_URL=
# PETPOOJA_ORDER_STATUS_URL=
```

## How menu sync works now (inbound-only)
1. Set the environment variables above and deploy with a real `PUBLIC_BASE_URL`.
2. Give PetPooja's integrations team your `/petpooja/push-menu` URL so they
   can configure it as your restaurant's Push Menu webhook target.
3. Whenever the manager edits the menu in PetPooja, it gets pushed to us
   automatically — no manual trigger needed.
4. Check `/admin/menu-status?token=YOUR_ADMIN_TOKEN` to see which PetPooja
   category ids have been seen and which still need mapping.
5. Open `category_map.json` and add each relevant PetPooja `category_id`
   under the matching `our_category_key` (e.g. `"veg_starters": ["10", "11"]`).
   The next menu push will pick up the mapping automatically.

## Order push & status webhook
- `/placeorder` builds a real Save Order payload (`build_petpooja_order_payload`
  in `app.py`, matching PetPooja's documented `OrderInfo/Customer/Order/
  OrderItem/Tax/Discount` structure) and calls `petpooja_client.push_order()`.
- Every KOT records `push_status` (`PENDING`/`SENT`/`FAILED`/`CANCELLED`),
  `petpooja_order_id` (PetPooja's own id), and `client_order_id` (ours —
  used to match incoming callbacks) so failures are visible instead of silent.
- `/petpooja/callback` receives kitchen-status updates and records them in
  `kitchen_status`; a `-1` (Cancelled) status auto-frees the table if no
  other unpaid orders remain.
- Manual test without live PetPooja:
  `curl -X POST <app>/petpooja/callback -H "Content-Type: application/json" -d "{\"orderID\":\"KOT101\",\"status\":\"-1\"}"`

## Admin routes are token-protected
`/admin/settle-table` and `/admin/menu-status` require an `ADMIN_TOKEN` env
var to be set. Pass it as `?token=...` or an `X-Admin-Token` header. **With
no `ADMIN_TOKEN` configured, both routes return 503 (blocked)** rather than
being left open — set a real token before deploying.

## Production checklist (before deploying)
- [ ] `SECRET_KEY` — set to a real random value (`python -c "import secrets; print(secrets.token_hex(32))"`)
- [ ] `FLASK_DEBUG=0` — never leave debug mode on in production
- [ ] `ADMIN_TOKEN` — set to a real random value, keep it secret
- [ ] `PUBLIC_BASE_URL` — real public HTTPS URL, so PetPooja's callback can reach you
- [ ] Run with a single worker (`Procfile` already pins `--workers 1`) —
  SQLite assumes a single process; scaling workers can cause
  "database is locked" errors
- [ ] Real PetPooja credentials (`PETPOOJA_APP_KEY/SECRET/ACCESS_TOKEN/REST_ID`)
- [ ] Give PetPooja your `/petpooja/push-menu` URL and confirm your `callback_url`
      is being hit correctly in their sandbox before going live
- [ ] Get written confirmation from PetPooja on the "bill paid" open question above

## Testing without live credentials
`test_menu_sync.py` verifies the normalize → category-map → build-menu
pipeline against a sample PetPooja-shaped payload. Run: `python test_menu_sync.py`
