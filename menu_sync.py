"""
Turns a raw PetPooja "Get Menu" response into the same shape our app already
uses internally: { our_category_key: [ {"name":.., "price":.., "petpooja_item_id":..}, ... ] }

Two layers of defense against not having the real PetPooja schema yet:

1. `normalize_petpooja_menu()` tries several common field-name variants for
   each value (e.g. item id could be "item_id" or "id"), so a small schema
   difference won't crash the whole sync.
2. `category_map.json` binds PetPooja's raw category ids/names to OUR
   existing curated category keys (veg_soups, veg_starters, ...) that the
   templates already expect. Fill this in once you can see real category
   ids from a live PetPooja menu pull — see PETPOOJA_SETUP.md.
"""

import json
import os

CATEGORY_MAP_PATH = os.path.join(os.path.dirname(__file__), "category_map.json")


def _first_present(d, keys, default=None):
    for key in keys:
        if key in d and d[key] not in (None, ""):
            return d[key]
    return default


def load_category_map():
    if not os.path.exists(CATEGORY_MAP_PATH):
        return {}
    with open(CATEGORY_MAP_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_petpooja_menu(raw_json):
    """
    Returns a flat list of normalized items:
    [{petpooja_item_id, petpooja_category_id, petpooja_category_name,
      name, price, is_veg, active}, ...]
    """
    data = raw_json.get("data", raw_json)  # some responses wrap payload in "data"

    categories = data.get("categories", [])
    category_name_by_id = {
        str(_first_present(cat, ["category_id", "id"])): _first_present(
            cat, ["category_name", "name"], ""
        )
        for cat in categories
    }

    items = data.get("items", [])
    normalized = []

    for item in items:
        item_id = _first_present(item, ["item_id", "id", "itemid"])
        name = _first_present(item, ["item_name", "name", "itemname"])
        price_raw = _first_present(item, ["item_price", "price", "itemprice"], 0)
        category_id = str(_first_present(item, ["category_id", "categoryid"], ""))
        is_veg_raw = _first_present(item, ["is_veg", "item_attributeid", "veg"], True)
        active_raw = _first_present(item, ["item_status", "active", "status"], 1)

        if item_id is None or not name:
            continue  # skip anything we can't safely use

        try:
            price = float(price_raw)
        except (TypeError, ValueError):
            price = 0.0

        normalized.append({
            "petpooja_item_id": str(item_id),
            "petpooja_category_id": category_id,
            "petpooja_category_name": category_name_by_id.get(category_id, ""),
            "name": name,
            "price": price,
            "is_veg": bool(is_veg_raw) if not isinstance(is_veg_raw, str) else is_veg_raw not in ("0", "false", "no"),
            "active": str(active_raw) not in ("0", "false", "no", "False"),
        })

    return normalized


def build_restaurant_menu(normalized_items, category_map):
    """
    Groups normalized PetPooja items into our existing UI category keys
    using category_map: { our_category_key: [petpooja_category_id, ...] }
    """
    petpooja_id_to_our_key = {}
    for our_key, petpooja_ids in category_map.items():
        for pid in petpooja_ids:
            petpooja_id_to_our_key[str(pid)] = our_key

    menu = {our_key: [] for our_key in category_map.keys()}

    for item in normalized_items:
        if not item["active"]:
            continue

        our_key = petpooja_id_to_our_key.get(item["petpooja_category_id"])
        if not our_key:
            continue  # category not mapped yet — skip until category_map.json is filled in

        menu[our_key].append({
            "name": item["name"],
            "price": item["price"],
            "petpooja_item_id": item["petpooja_item_id"],
        })

    return menu
