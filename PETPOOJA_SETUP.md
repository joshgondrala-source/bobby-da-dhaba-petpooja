# PetPooja Integration Setup (Phase 3: Menu Sync)

## What's built
- `petpooja_client.py` — thin HTTP client for PetPooja's Get Menu & Save Order APIs.
- `menu_sync.py` — normalizes PetPooja's raw menu response into our app's format, defensively
  handling a few common field-name variants (since the exact schema wasn't available yet).
- `category_map.json` — maps PetPooja's raw `category_id`s to our existing UI category keys
  (`veg_soups`, `veg_starters`, etc. — the ones already baked into `veg.html`/`nonveg.html`).
- `/admin/sync-menu` — manually triggers a live pull from PetPooja, caches items in the
  `petpooja_items` SQLite table, and reports which PetPooja category ids still need mapping.
- Until PetPooja is configured/synced, the app keeps using the original hardcoded menu
  (`FALLBACK_MENU` in `app.py`) — nothing breaks locally without credentials.

## ⚠️ Field names are placeholders
The exact PetPooja request/response schema is partner-specific and wasn't available while
building this. Everything that's a guess is marked `# PLACEHOLDER` in `petpooja_client.py`.
Once you have PetPooja's real API docs (Postman collection / PDF from your onboarding
manager), update:
1. `PETPOOJA_MENU_URL` / `PETPOOJA_SAVE_ORDER_URL` (or the base URL env var)
2. The request payload shape in `PetPoojaClient.fetch_menu()` / `push_order()`
3. The response field names read in `menu_sync.normalize_petpooja_menu()`

Nothing else needs to change — the rest of the app only talks to `menu_sync`'s normalized output.

## Environment variables to set
```
PETPOOJA_APP_KEY=...
PETPOOJA_APP_SECRET=...
PETPOOJA_ACCESS_TOKEN=...
PETPOOJA_REST_ID=...
# optional overrides once you have the real endpoints:
PETPOOJA_BASE_URL=...
PETPOOJA_MENU_URL=...
PETPOOJA_SAVE_ORDER_URL=...
PETPOOJA_ORDER_STATUS_URL=...
```

## How to sync the real menu once credentials are set
1. Set the environment variables above and restart the app.
2. Visit `/admin/sync-menu?token=YOUR_ADMIN_TOKEN` — it will report `items_synced`, plus a list of
   `raw_categories_seen` (PetPooja's real category ids/names) and `unmapped_category_ids`.
3. Open `category_map.json` and add each relevant PetPooja `category_id` under the matching
   `our_category_key` (e.g. `"veg_starters": ["10", "11"]`).
4. Call `/admin/sync-menu?token=...` again — mapped categories will now show PetPooja's live
   items/prices instead of the fallback ones.

## Order push & settlement polling (Phase 4/5)
- `/placeorder` builds a Save Order payload (see `build_petpooja_order_payload` in `app.py`) and
  calls `petpooja_client.push_order()`. Every KOT records `push_status`
  (`PENDING`/`SENT`/`FAILED`/`CANCELLED`) and `petpooja_order_id` so failures are visible instead
  of silent.
- A background thread polls `petpooja_client.get_order_status()` every ~20s for any table with
  `SENT` orders still marked unpaid. Once PetPooja reports an order as settled/paid **or**
  cancelled/voided, that order is closed out locally; once a table has zero remaining unpaid
  orders, it's auto-cleared (customer info wiped, ready for the next guest).
- Manual trigger for testing: `/admin/poll-settlements?token=YOUR_ADMIN_TOKEN`.

## Admin routes are token-protected
`/admin/sync-menu` and `/admin/poll-settlements` require an `ADMIN_TOKEN` env var to be set.
Pass it as `?token=...` or an `X-Admin-Token` header. **With no `ADMIN_TOKEN` configured, both
routes return 503 (blocked) rather than being left open** — set a real token before deploying.

## Production checklist (before deploying)
- [ ] `SECRET_KEY` — set to a real random value (`python -c "import secrets; print(secrets.token_hex(32))"`)
- [ ] `FLASK_DEBUG=0` — never leave debug mode on in production
- [ ] `ADMIN_TOKEN` — set to a real random value, keep it secret
- [ ] Run with a single worker (`Procfile` already pins `--workers 1`) — the settlement-poller
  thread and SQLite both assume a single process; scaling workers would duplicate polling and
  can cause "database is locked" errors
- [ ] Real PetPooja credentials + corrected placeholder fields (see the warning above)

## Testing without live credentials
`test_menu_sync.py` verifies the normalize → category-map → build-menu pipeline against a
sample PetPooja-shaped payload. Run: `python test_menu_sync.py`

