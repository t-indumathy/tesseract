"""Shopping Agent — full UCP + AP2 flow via Google ADK.

Run:
    uv run python src/agent/shopping_agent.py        # standalone demo
    uv run python src/agent/shopping_agent.py adk    # ADK + Gemini
"""
from __future__ import annotations
import os
from dotenv import load_dotenv

load_dotenv()

try:
    from google.adk.agents import Agent
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    ADK_AVAILABLE = True
except ImportError:
    ADK_AVAILABLE = False

from src.agent.tools import (
    discover_merchant_capabilities,
    search_catalog,
    create_cart,
    request_user_confirmation,
    checkout,
    get_checkout_session,
)


def run_demo_flow(query: str = "headphones", user_id: str = "user-demo-123"):
    """Full UCP + AP2 flow without ADK. No API key needed."""
    print("=" * 62)
    print(" Tesseract — UCP + AP2 Agentic Commerce PoC (spec-compliant)")
    print("=" * 62)

    print("\n[1/6] Discovering merchant capabilities (/.well-known/ucp)...")
    profile = discover_merchant_capabilities()
    caps = list(profile["ucp"]["capabilities"].keys())
    print(f"  UCP version : {profile['ucp']['version']}")
    print(f"  Capabilities: {caps}")
    ap2_supported = "dev.ucp.shopping.ap2_mandate" in caps
    print(f"  AP2 mandate : {'✓ supported' if ap2_supported else '✗ not declared'}")

    print(f"\n[2/6] Searching catalog: '{query}'...")
    results = search_catalog(query)
    # Show negotiated capabilities echoed back in response
    resp_caps = list(results["ucp"]["capabilities"].keys())
    print(f"  Response ucp.capabilities: {resp_caps}")  # spec: MUST be echoed
    product = results["products"][0]
    print(f"  Selected    : {product['name']} — ${product['price_usd']}")

    print(f"\n[3/6] Creating UCP cart (POST /ucp/v1/carts)...")
    cart = create_cart(product_id=product["id"], quantity=1)
    totals = cart["totals"]
    print(f"  Cart ID     : {cart['id']}")
    print(f"  Subtotal    : {totals['subtotal']} cents (${totals['subtotal']/100:.2f})")
    print(f"  Tax         : {totals['tax']} cents")
    print(f"  Total       : {totals['total']} cents (${totals['total']/100:.2f})")
    print(f"  (Amounts in minor units / cents — per UCP spec)")

    print("\n[4/6] Issuing AP2 Intent + Cart Mandates (user confirmation)...")
    intent_mandate, cart_mandate = request_user_confirmation(
        user_id=user_id, cart=cart, spending_limit_usd=500.0,
    )
    print(f"  Intent Mandate ID : {intent_mandate['id']}")
    print(f"  Cart Mandate ID   : {cart_mandate['id']}")
    print(f"  Proof type        : {intent_mandate['proof']['type']}")
    print(f"  (dev.ucp.shopping.ap2_mandate extension active)")

    print("\n[5/6] Checkout (POST /ucp/v1/checkout-sessions)...")
    print("  Merchant will verify mandates before completing session.")
    session = checkout(
        cart_id=cart["id"],
        intent_mandate=intent_mandate,
        cart_mandate=cart_mandate,
    )
    print(f"  Session ID  : {session['id']}")
    print(f"  Status      : {session['status']}")
    print(f"  Total (¢)   : {session['total_amount']}")
    print(f"  Response ucp.capabilities: {list(session['ucp']['capabilities'].keys())}")

    print("\n[6/6] Fetching checkout session status...")
    status = get_checkout_session(session["id"])
    print(f"  Status : {status['status']} | Total: {status['total_amount']} cents")
    print(f"  Message: {status['message']}")

    print("\n" + "=" * 62)
    print(" PoC complete. Full spec-compliant UCP + AP2 flow verified.")
    print("=" * 62)


def run_adk_agent(user_message: str = "Buy me a good pair of headphones."):
    if not ADK_AVAILABLE:
        print("google-adk not installed. Run: uv sync")
        return

    agent = Agent(
        name="tesseract_shopping_agent",
        model="gemini-2.5-flash",
        description="Agentic shopping assistant using UCP + AP2.",
        instruction=(
            "You are a shopping agent. To complete a purchase: "
            "1) discover_merchant_capabilities — check UCP profile and AP2 support. "
            "2) search_catalog — find what the user wants. "
            "3) create_cart — build the cart; note totals are in cents (divide by 100 for USD). "
            "4) request_user_confirmation — ALWAYS do this; never skip AP2 mandates. "
            "5) checkout — submit with both mandates; merchant verifies them. "
            "6) get_checkout_session — confirm status. "
            "Always tell the user the total in USD before confirming."
        ),
        tools=[
            discover_merchant_capabilities,
            search_catalog,
            create_cart,
            request_user_confirmation,
            checkout,
            get_checkout_session,
        ],
    )

    session_service = InMemorySessionService()
    runner = Runner(agent=agent, app_name="tesseract", session_service=session_service)
    session = session_service.create_session(app_name="tesseract", user_id="demo-user")

    print(f"\nUser: {user_message}\n" + "-" * 40)
    for event in runner.run(
        user_id="demo-user",
        session_id=session.id,
        new_message=user_message,
    ):
        if event.is_final_response():
            print(f"Agent: {event.content.parts[0].text}")


if __name__ == "__main__":
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "demo"
    if mode == "adk":
        run_adk_agent()
    else:
        run_demo_flow()
