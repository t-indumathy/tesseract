# Copyright 2025 Google LLC  (Apache-2.0)
# Implements the UCP capability discovery endpoint per spec:
# https://ucp.dev/2026-04-08/specification/overview/
"""UCP manifest builder for the Tesseract merchant server.

Key spec requirements this file satisfies:
  - Served at `/.well-known/ucp`  (NOT `/.well-known/ucp-manifest`)
  - Capability names use reverse-domain notation: `dev.ucp.shopping.*`
  - `UCP-Agent` header is read and reflected in the `ucp.agent_profile` field
  - `payment_handlers` advertises AP2 as the accepted payment protocol
"""
from __future__ import annotations
import os
from typing import Any

MERCHANT_ID = os.getenv("MERCHANT_ID", "tesseract-demo-merchant")
BASE_URL = os.getenv("MERCHANT_BASE_URL", "http://localhost:8080")


def build_manifest(ucp_agent_header: str | None = None) -> dict[str, Any]:
    """
    Returns the UCP manifest dict.

    The `ucp` top-level key is required by the spec. Every capability name
    MUST use reverse-domain notation. The `payment_handlers` block tells
    shopping agents which payment protocols this merchant accepts.

    Ref: https://ucp.dev/2026-04-08/specification/overview/
    """
    return {
        "ucp": {
            "version": "2026-04-08",
            "merchant": {
                "id": MERCHANT_ID,
                "name": "Tesseract Demo Store",
                "website": BASE_URL,
            },
            # agent_profile echoes back the UCP-Agent header if provided
            "agent_profile": ucp_agent_header or "",
            "capabilities": {
                # Reverse-domain capability names — required by spec
                "dev.ucp.shopping.catalog_search": [
                    {"version": "2026-04-08", "endpoint": f"{BASE_URL}/ucp/catalog/search"}
                ],
                "dev.ucp.shopping.cart": [
                    {"version": "2026-04-08", "endpoint": f"{BASE_URL}/ucp/cart"}
                ],
                "dev.ucp.shopping.checkout": [
                    {"version": "2026-04-08", "endpoint": f"{BASE_URL}/ucp/checkout"}
                ],
                "dev.ucp.shopping.order_management": [
                    {"version": "2026-04-08", "endpoint": f"{BASE_URL}/ucp/order/{{order_id}}"}
                ],
            },
            # payment_handlers: which AP2 flows this merchant accepts
            "payment_handlers": {
                "ap2": {
                    "supported": True,
                    # HNP = Hosted Network Payment (AP2 default flow)
                    # DPC = Digital Payment Credential (wallet-bound flow)
                    "flows": ["HNP", "DPC"],
                    "mandate_types": ["CheckoutMandate", "PaymentMandate"],
                }
            },
        }
    }
