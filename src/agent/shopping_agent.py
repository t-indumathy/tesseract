"""Shopping Agent — orchestrates the full UCP + AP2 flow using Google ADK.

Run:
    uv run python src/agent/shopping_agent.py
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
    print("[WARN] google-adk not installed. Running in standalone demo mode.")

from src.agent.tools import (
    discover_merchant_capabilities,
    search_catalog,
    create_cart,
    request_user_confirmation,
    checkout,
    get_order_status,
)


# ── Standalone demo (no ADK required) ─────────────────────────
def run_demo_flow(query: str = "headphones", user_id: str = "user-demo-123"):
    """
    Runs the full UCP + AP2 commerce flow without the ADK layer.
    Useful for quick PoC validation without a Gemini API key.
    """
    print("=" * 60)
    print("TESSERACT — UCP + AP2 Agentic Commerce PoC")
    print("=" * 60)

    # Step 1: Discover
    print("\n[1] Discovering merchant capabilities (UCP manifest)...")
    manifest = discover_merchant_capabilities()
    caps = [c["name"] for c in manifest["capabilities"]]
    print(f"    Merchant: {manifest['merchant_name']}")
    print(f"    AP2 supported: {manifest['ap2_supported']}")
    print(f"    Capabilities: {caps}")

    # Step 2: Search catalog
    print(f"\n[2] Searching catalog for: '{query}'...")
    results = search_catalog(query)
    product = results["products"][0]
    print(f"    Found: {product['name']} — ${product['price_usd']}")

    # Step 3: Build cart
    print(f"\n[3] Building UCP cart for product {product['id']}...")
    cart = create_cart(product_id=product["id"], quantity=1)
    print(f"    Cart ID: {cart['cart_id']}")
    print(f"    Subtotal: ${cart['subtotal_usd']} | Tax: ${cart['tax_usd']} | Total: ${cart['total_usd']}")

    # Step 4: AP2 mandate issuance (user confirmation)
    print("\n[4] Issuing AP2 Intent + Cart Mandates...")
    intent_mandate, cart_mandate = request_user_confirmation(
        user_id=user_id,
        cart=cart,
        spending_limit_usd=500.0,
    )
    print(f"    Intent Mandate ID: {intent_mandate['id']}")
    print(f"    Cart Mandate ID:   {cart_mandate['id']}")
    print(f"    Proof type: {intent_mandate['proof']['type']}")

    # Step 5: Checkout (UCP + AP2 verification)
    print("\n[5] Submitting UCP checkout with AP2 mandates...")
    order = checkout(
        cart_id=cart["cart_id"],
        intent_mandate=intent_mandate,
        cart_mandate=cart_mandate,
    )
    print(f"    Order ID: {order['order_id']}")
    print(f"    Status:   {order['status']}")
    print(f"    Message:  {order['message']}")

    # Step 6: Order status
    print("\n[6] Fetching order status (UCP order management)...")
    status = get_order_status(order["order_id"])
    print(f"    Order confirmed: ${status['total_usd']} | Status: {status['status']}")

    print("\n" + "=" * 60)
    print("PoC complete. Full UCP + AP2 flow verified.")
    print("=" * 60)


# ── ADK Agent (requires GOOGLE_API_KEY) ───────────────────────
def run_adk_agent(user_message: str = "I want to buy a good pair of headphones."):
    """Run the Shopping Agent via Google ADK with Gemini."""
    if not ADK_AVAILABLE:
        print("google-adk is not installed. Run 'uv sync' first.")
        return

    agent = Agent(
        name="tesseract_shopping_agent",
        model="gemini-2.5-flash",
        description="An AI shopping agent that uses UCP for commerce and AP2 for payments.",
        instruction=(
            "You are a helpful shopping agent. "
            "To help the user buy something: "
            "1) discover_merchant_capabilities to see what the store supports, "
            "2) search_catalog with the user's request, "
            "3) create_cart with the best product, "
            "4) request_user_confirmation to get AP2 mandates (always do this — never skip), "
            "5) checkout with the mandates, "
            "6) get_order_status to confirm. "
            "Always show the user the total price BEFORE confirming."
        ),
        tools=[
            discover_merchant_capabilities,
            search_catalog,
            create_cart,
            request_user_confirmation,
            checkout,
            get_order_status,
        ],
    )

    session_service = InMemorySessionService()
    runner = Runner(agent=agent, app_name="tesseract", session_service=session_service)
    session = session_service.create_session(app_name="tesseract", user_id="demo-user")

    print(f"\nUser: {user_message}")
    print("-" * 40)

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
