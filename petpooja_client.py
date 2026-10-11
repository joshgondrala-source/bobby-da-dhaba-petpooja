"""
HTTP client for PetPooja's Partner APIs — PetpoojaOnlineOrdering APIs V2.1.0.

Based on the real API blueprint shared by PetPooja's integrations team
(Oct 2026), not guesses. Key facts that shaped this client:

  - Menu sync is INBOUND, not outbound: PetPooja calls a "Push Menu" webhook
    on OUR server whenever the restaurant's menu changes in PetPooja. There
    is no "fetch menu" endpoint for us to call (the old Fetch Menu API is
    deprecated). See /petpooja/push-menu in app.py.

  - There is NO "get order status" / polling endpoint. Order status (kitchen
    state, not payment/settlement) is delivered via a webhook: we must pass
    a `callback_url` in every Save Order request, and PetPooja POSTs status
    changes to that URL. See /petpooja/callback in app.py.

  - The only status WE can push back to PetPooja is cancelling a still
    pending order (status=-1), via the Update Order Status endpoint.

  - There is no documented "bill settled/paid" signal at all in this API —
    only kitchen states (accepted/dispatched/food ready/delivered/cancelled).
    This must still be confirmed with PetPooja directly (see
    PETPOOJA_SETUP.md's "Open question for PetPooja" section).
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

        # Real dev/sandbox URLs from PetPooja's V2.1.0 API docs. Production
        # URLs are shared separately per-partner once onboarding completes —
        # override via env vars at that point, no code change needed.
        self.save_order_url = os.environ.get(
            "PETPOOJA_SAVE_ORDER_URL",
            "https://47pfzh5sf2.execute-api.ap-southeast-1.amazonaws.com/V1/save_order",
        )
        self.update_order_status_url = os.environ.get(
            "PETPOOJA_ORDER_STATUS_URL",
            "https://qle1yy2ydc.execute-api.ap-southeast-1.amazonaws.com/V1/update_order_status",
        )

    def is_configured(self):
        return bool(self.app_key and self.app_secret and self.access_token and self.rest_id)

    def _auth_fields(self):
        return {
            "app_key": self.app_key,
            "app_secret": self.app_secret,
            "access_token": self.access_token,
        }

    def push_order(self, orderinfo, udid="", device_type="Web", timeout=15):
        """
        Calls PetPooja's Save Order endpoint.

        `orderinfo` must already be shaped like the real API's "orderinfo"
        object: {"OrderInfo": {"Restaurant": {...}}, "Customer": {...},
        "Order": {...}, "OrderItem": {...}, "Tax": {...}, "Discount": {...}}
        — see app.py's build_petpooja_order_payload().

        Returns the parsed JSON response. Raises PetPoojaError on network
        failure or when PetPooja reports success != "1" (e.g. validation
        errors like a missing orderID or item name).
        """
        if not self.is_configured():
            raise PetPoojaError(
                "PetPooja credentials are not set. Configure PETPOOJA_APP_KEY, "
                "PETPOOJA_APP_SECRET, PETPOOJA_ACCESS_TOKEN and PETPOOJA_REST_ID."
            )

        payload = {
            **self._auth_fields(),
            "orderinfo": orderinfo,
            "udid": udid,
            "device_type": device_type,
        }

        try:
            response = requests.post(self.save_order_url, json=payload, timeout=timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise PetPoojaError(f"Failed to push order to PetPooja: {exc}") from exc

        data = response.json()

        if str(data.get("success")) != "1":
            errors = data.get("validation_errors")
            message = data.get("message", "PetPooja rejected the order")
            raise PetPoojaError(f"{message} ({errors})" if errors else message)

        return data

    def cancel_order(self, client_order_id, cancel_reason, petpooja_order_id="", timeout=15):
        """
        Calls PetPooja's Update Order Status endpoint. This is the ONLY
        status-changing call available to us, and it only supports
        cancelling a still-pending order (status=-1) — there is no generic
        "set status" endpoint.
        """
        if not self.is_configured():
            raise PetPoojaError(
                "PetPooja credentials are not set. Configure PETPOOJA_APP_KEY, "
                "PETPOOJA_APP_SECRET, PETPOOJA_ACCESS_TOKEN and PETPOOJA_REST_ID."
            )

        payload = {
            **self._auth_fields(),
            "restID": self.rest_id,
            # "orderID" is PetPooja's own id for the order; it's being
            # deprecated by them in favour of clientorderID, so we always
            # send it blank per their docs and rely on clientorderID instead.
            "orderID": petpooja_order_id or "",
            "clientorderID": client_order_id,
            "cancelReason": cancel_reason,
            "status": "-1",
        }

        try:
            response = requests.post(self.update_order_status_url, json=payload, timeout=timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise PetPoojaError(f"Failed to cancel order in PetPooja: {exc}") from exc

        return response.json()
