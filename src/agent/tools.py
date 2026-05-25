"""UCP + AP2 tool bindings for the Shopping Agent.

These are Google ADK FunctionTool-compatible callables.
The agent uses these to interact with the UCP merchant server and AP2 mandate flow.
"""
from __future__ import annotations
import os
import httpx
from src.ap2.mandates import issue_intent_mandate, issue_cart_mandate

BASE_URL = os.getenv("MERCHANT_BASE_URL", "http://localhost:8080")
AGENT_ID = "tesseract-shopping-agent-v1"
MERCHANT_ID = os.getenv("MERCHANT_ID", "tesseract-demo-merchant")


def discover_merchant_capabilities() -> dict:
    """(UCP) Discover what the merchant supports before any transaction."""
    with httpx.Client() as client:
        resp = client.get(f"{BASE_URL}/.well-known/ucp-manifest")
        resp.raise_for_status()
        return resp.json()


def search_catalog(query: str, max_results: int = 5) -> dict:
    """(UCP) Search the merchant's product catalog."""
    with httpx.Client() as client:
        resp = client.post(
            f"{BASE_URL}/ucp/catalog/search",
            json={"query": query, "max_results": max_results},
        )
        resp.raise_for_status()
        return resp.json()


def create_cart(product_id: str, quantity: int = 1) -> dict:
    """(UCP) Add a product to a cart and get pricing with tax."""
    with httpx.Client() as client:
        resp = client.post(
            f"{BASE_URL}/ucp/cart",
            json={
                "items": [{"product_id": product_id, "quantity": quantity}],
                "buyer_agent_id": AGENT_ID,
            },
        )
        resp.raise_for_status()
        return resp.json()


def request_user_confirmation(
    user_id: str,
    cart: dict,
    spending_limit_usd: float = 500.0,
) -> tuple[dict, dict]:
    """
    (AP2) Simulate user confirmation and issue Intent + Cart Mandates.

    In a real deployment this step surfaces a consent UI to the human user.
    Here we auto-confirm for PoC purposes but still go through the full
    AP2 mandate issuance path so the cryptographic trail exists.
    """
    print(f"\n[AP2] Requesting user confirmation for cart {cart['cart_id']}")
    print(f"      Total: ${cart['total_usd']} | Items: {len(cart['items'])}")
    print("      [PoC] Auto-confirming...\n")

    intent_mandate = issue_intent_mandate(
        user_id=user_id,
        agent_id=AGENT_ID,
        merchant_id=MERCHANT_ID,
        action="purchase",
        spending_limit_usd=spending_limit_usd,
    )
    cart_mandate = issue_cart_mandate(
        cart_id=cart["cart_id"],
        cart_total_usd=cart["total_usd"],
        items=cart["items"],
        agent_id=AGENT_ID,
        merchant_id=MERCHANT_ID,
    )
    return intent_mandate, cart_mandate


def checkout(
    cart_id: str,
    intent_mandate: dict,
    cart_mandate: dict,
) -> dict:
    """(UCP + AP2) Submit checkout with AP2 mandates for merchant verification."""
    with httpx.Client() as client:
        resp = client.post(
            f"{BASE_URL}/ucp/checkout",
            json={
                "cart_id": cart_id,
                "intent_mandate": intent_mandate,
                "cart_mandate": cart_mandate,
                "payment_token": "mock-payment-token",
            },
        )
        resp.raise_for_status()
        return resp.json()


def get_order_status(order_id: str) -> dict:
    """(UCP) Fetch order status post-checkout."""
    with httpx.Client() as client:
        resp = client.get(f"{BASE_URL}/ucp/order/{order_id}")
        resp.raise_for_status()
        return resp.json()
