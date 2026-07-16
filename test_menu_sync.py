"""
Quick sanity check for menu_sync.py against a SAMPLE PetPooja-shaped payload
(field names are best-guess placeholders — see petpooja_client.py notes).
Run: python test_menu_sync.py
"""

from menu_sync import normalize_petpooja_menu, build_restaurant_menu

SAMPLE_PETPOOJA_RESPONSE = {
    "status": "success",
    "data": {
        "categories": [
            {"category_id": "10", "category_name": "Starters"},
            {"category_id": "20", "category_name": "Soups"},
        ],
        "items": [
            {
                "item_id": "101",
                "item_name": "Paneer Tikka",
                "category_id": "10",
                "item_price": "299",
                "is_veg": True,
                "item_status": 1,
            },
            {
                "item_id": "102",
                "item_name": "Chicken 65",
                "category_id": "10",
                "item_price": "289",
                "is_veg": False,
                "item_status": 1,
            },
            {
                "item_id": "103",
                "item_name": "Sweet Corn Soup Veg",
                "category_id": "20",
                "item_price": "99",
                "is_veg": True,
                "item_status": 0,  # inactive — should be filtered out
            },
        ],
    },
}

SAMPLE_CATEGORY_MAP = {
    "veg_tikka": ["10"],
    "veg_soups": ["20"],
}


def main():
    normalized = normalize_petpooja_menu(SAMPLE_PETPOOJA_RESPONSE)
    assert len(normalized) == 3, f"expected 3 normalized items, got {len(normalized)}"

    active_items = [i for i in normalized if i["active"]]
    assert len(active_items) == 2, f"expected 2 active items, got {len(active_items)}"

    menu = build_restaurant_menu(normalized, SAMPLE_CATEGORY_MAP)
    assert menu["veg_tikka"][0]["name"] == "Paneer Tikka"
    assert menu["veg_tikka"][0]["price"] == 299.0
    assert menu["veg_soups"] == [], "inactive item must be filtered out"

    print("All menu_sync assertions passed.")
    print("Normalized items:", normalized)
    print("Built menu:", menu)


if __name__ == "__main__":
    main()
