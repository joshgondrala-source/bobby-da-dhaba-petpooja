"""
Thin HTTP client for PetPooja's Partner APIs.

IMPORTANT: The exact endpoint paths and JSON field names below are
PLACEHOLDERS. PetPooja does not publish one universal public schema — the
real request/response shape is shared per-partner during onboarding
(Postman collection / PDF from your PetPooja integration manager).

Everything that is a guess is marked with `# PLACEHOLDER`. Once you have the
real docs, update:
  1. The two endpoint URLs (PETPOOJA_MENU_URL / PETPOOJA_SAVE_ORDER_URL)
  2. The request payload shape in fetch_menu() / push_order()
  3. The response field names read in menu_sync.normalize_petpooja_menu()

Nothing else in the app needs to change — every other module only talks to
this client and to menu_sync's normalized output.
"""

import os
import requests


class PetPoojaError(Exception):
    """Raised when PetPooja credentials are missing or a call fails."""


class PetPoojaClient:
    def __init__(self):
        self.app_key = os.environ.get("PETPOOJA_APP_KEY")
        self.app_secret = os.environ.get("PETPOOJA_APP_SECRET")
        self.access_token = os.environ.get("PETPOOJA_ACCESS_TOKEN")
        self.rest_id = os.environ.get("PETPOOJA_REST_ID")

        # PLACEHOLDER — replace with the real base URL from PetPooja's docs
        # once available (their public sandbox uses an apiary mock domain
        # during partner onboarding; production has its own URL per partner).
        self.base_url = os.environ.get(
            "PETPOOJA_BASE_URL",
            "https://qle1yy2ydc.execute-api.ap-southeast-1.amazonaws.com/V1",
        )
        self.menu_url = os.environ.get(
            "PETPOOJA_MENU_URL", f"{self.base_url}/menu"  # PLACEHOLDER path
        )
        self.save_order_url = os.environ.get(
            "PETPOOJA_SAVE_ORDER_URL", f"{self.base_url}/order/save_order"  # PLACEHOLDER path
        )
        self.order_status_url = os.environ.get(
            "PETPOOJA_ORDER_STATUS_URL", f"{self.base_url}/order/status"  # PLACEHOLDER path
        )

    def is_configured(self):
        return bool(self.app_key and self.app_secret and self.access_token and self.rest_id)

    def _auth_payload(self):
        return {
            "app_key": self.app_key,
            "app_secret": self.app_secret,
            "access_token": self.access_token,
            "restID": self.rest_id,
        }

    def fetch_menu(self, timeout=15):
        """Calls PetPooja's Get Menu endpoint and returns the raw JSON response."""
        if not self.is_configured():
            raise PetPoojaError(
                "PetPooja credentials are not set. Configure PETPOOJA_APP_KEY, "
                "PETPOOJA_APP_SECRET, PETPOOJA_ACCESS_TOKEN and PETPOOJA_REST_ID."
            )

        payload = self._auth_payload()  # PLACEHOLDER — confirm exact request body shape

        try:
            response = requests.post(self.menu_url, json=payload, timeout=timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise PetPoojaError(f"Failed to fetch menu from PetPooja: {exc}") from exc

        return response.json()

    def push_order(self, order_payload, timeout=15):
        """Calls PetPooja's Save Order endpoint. Used from Phase 4 onward."""
        if not self.is_configured():
            raise PetPoojaError(
                "PetPooja credentials are not set. Configure PETPOOJA_APP_KEY, "
                "PETPOOJA_APP_SECRET, PETPOOJA_ACCESS_TOKEN and PETPOOJA_REST_ID."
            )

        payload = {**self._auth_payload(), **order_payload}  # PLACEHOLDER — confirm shape

        try:
            response = requests.post(self.save_order_url, json=payload, timeout=timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise PetPoojaError(f"Failed to push order to PetPooja: {exc}") from exc

        return response.json()

    def get_order_status(self, petpooja_order_id, timeout=15):
        """
        Calls PetPooja's order status endpoint (PLACEHOLDER path/shape) — used by
        the Phase 5 settlement poller to detect when the manager has settled a
        table's bill in PetPooja, so we know when to auto-clear it locally.
        Expected response is guessed to contain a "status" field; correct once
        real docs are available (see PETPOOJA_SETUP.md).
        """
        if not self.is_configured():
            raise PetPoojaError(
                "PetPooja credentials are not set. Configure PETPOOJA_APP_KEY, "
                "PETPOOJA_APP_SECRET, PETPOOJA_ACCESS_TOKEN and PETPOOJA_REST_ID."
            )

        payload = {**self._auth_payload(), "order_id": petpooja_order_id}  # PLACEHOLDER — confirm shape

        try:
            response = requests.post(self.order_status_url, json=payload, timeout=timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise PetPoojaError(f"Failed to fetch order status from PetPooja: {exc}") from exc

        return response.json()
