"""UCP + AP2 tool callables for the Shopping Agent (ADK-compatible).

Key spec compliance in this file:
  - Every request includes UCP-Agent header (RFC 8941 Dictionary Structured Field)
    profile URL points to /platform-profile on the merchant server (local PoC)
  - All amounts interpreted in minor units (cents) when received from UCP
  - Endpoint paths follow UCP REST spec:
      POST /ucp/v1/carts
      POST /ucp/v1/checkout-sessions
"""
from __future__ import annotations
import os
import httpx
from src.ap2.mandates import issue_intent_mandate, issue_cart_mandate

BASE_URL = os.getenv("MERCHANT_BASE_URL", "http://localhost:8080")
AGENT_ID = "tesseract-shopping-agent-v1"
MERCHANT_ID = os.getenv("MERCHANT_ID", "tesseract-demo-merchant")
PLATFORM_PROFILE_URL = os.getenv("PLATFORM_PROFILE_URL", f"{BASE_URL}/platform-profile")

# RFC 8941 Dictionary Structured Field for UCP-Agent header
# Spec: https://ucp.dev/2026-04-08/specification/overview/#platform-advertisement-on-request
_UCP_AGENT_HEADER = f'profile="{PLATFORM_PROFILE_URL}"'
_HEADERS = {"UCP-Agent": _UCP_AGENT_HEADER}


def discover_merchant_capabilities() -> dict:
    """
    (UCP) Fetch the merchant's capability profile from /.well-known/ucp.
    Spec profile shape: version + services + capabilities + payment_handlers.
    """
    with httpx.Client() as client:
        resp = client.get(f"{BASE_URL}/.well-known/ucp")
        resp.raise_for_status()
        return resp.json()


def search_catalog(query: str, max_results: int = 5) -> dict:
    """(UCP) Search catalog. Sends UCP-Agent header per spec."""
    with httpx.Client() as client:
        resp = client.post(
            f"{BASE_URL}/ucp/v1/catalog/search",
            json={"query": query, "max_results": max_results},
            headers=_HEADERS,
        )
        resp.raise_for_status()
        return resp.json()


def create_cart(product_id: str, quantity: int = 1) -> dict:
    """
    (UCP dev.ucp.shopping.cart) Create cart.
    UCP REST path: POST /ucp/v1/carts
    Returns totals in minor units (cents) per spec.
    """
    with httpx.Client() as client:
        resp = client.post(
            f"{BASE_URL}/ucp/v1/carts",
            json={
                "line_items": [{"product_id": product_id, "quantity": quantity}],
                "buyer_agent_id": AGENT_ID,
            },
            headers=_HEADERS,
        )
        resp.raise_for_status()
        return resp.json()


def request_user_confirmation(
    user_id: str,
    cart: dict,
    spending_limit_usd: float = 500.0,
) -> tuple[dict, dict]:
    """
    (AP2) Issue Intent Mandate + Cart Mandate after user confirmation.

    In production: surface a consent UI to the human user here.
    This PoC auto-confirms but still runs through the full AP2 mandate path
    so the cryptographic audit trail exists.
    """
    totals = cart["totals"]
    total_cents = totals["total"]
    total_usd = total_cents / 100

    print(f"\n[AP2] User confirmation requested")
    print(f"      Cart ID : {cart['id']}")
    print(f"      Total   : ${total_usd:.2f} (={total_cents} cents)")
    print(f"      [PoC] Auto-confirming — issuing AP2 mandates...\n")

    intent_mandate = issue_intent_mandate(
        user_id=user_id,
        agent_id=AGENT_ID,
        merchant_id=MERCHANT_ID,
        action="purchase",
        spending_limit_usd=spending_limit_usd,
    )
    cart_mandate = issue_cart_mandate(
        cart_id=cart["id"],
        cart_total_cents=total_cents,
        line_items=cart["line_items"],
        agent_id=AGENT_ID,
        merchant_id=MERCHANT_ID,
    )
    return intent_mandate, cart_mandate


def checkout(
    cart_id: str,
    intent_mandate: dict,
    cart_mandate: dict,
) -> dict:
    """
    (UCP dev.ucp.shopping.checkout + dev.ucp.shopping.ap2_mandate)
    POST /ucp/v1/checkout-sessions with AP2 mandate block.

    The `ap2` block maps to the dev.ucp.shopping.ap2_mandate extension field.
    The merchant verifies both VCs before completing the session.
    """
    with httpx.Client() as client:
        resp = client.post(
            f"{BASE_URL}/ucp/v1/checkout-sessions",
            json={
                "cart_id": cart_id,
                "ap2": {
                    "intent_mandate": intent_mandate,
                    "cart_mandate": cart_mandate,
                },
                "payment_token": "mock-payment-token",
            },
            headers=_HEADERS,
        )
        resp.raise_for_status()
        return resp.json()


def get_checkout_session(session_id: str) -> dict:
    """(UCP) Fetch checkout session status."""
    with httpx.Client() as client:
        resp = client.get(
            f"{BASE_URL}/ucp/v1/checkout-sessions/{session_id}",
            headers=_HEADERS,
        )
        resp.raise_for_status()
        return resp.json()
