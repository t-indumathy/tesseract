"""UCP Merchant Server — FastAPI implementation of UCP REST endpoints."""
from __future__ import annotations
import os
import uuid
from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv

from src.merchant.models import (
    UCPManifest, UCPCapability,
    CatalogSearchRequest, CatalogSearchResponse,
    CreateCartRequest, CartResponse, CartItem,
    CheckoutRequest, OrderResponse,
)
from src.merchant.catalog import search_products, get_product
from src.ap2.verifier import verify_mandate

load_dotenv()

app = FastAPI(
    title="Tesseract UCP Merchant Server",
    description="PoC UCP-compliant merchant server with AP2 mandate verification",
    version="0.1.0",
)

# In-memory stores (swap with DB for production)
_carts: dict[str, CartResponse] = {}
_orders: dict[str, OrderResponse] = {}

MERCHANT_ID = os.getenv("MERCHANT_ID", "tesseract-demo-merchant")


# ── UCP Capability Discovery ───────────────────────────────────
@app.get("/.well-known/ucp-manifest", response_model=UCPManifest)
async def get_ucp_manifest():
    """UCP capability discovery endpoint — agents call this first."""
    return UCPManifest(
        merchant_id=MERCHANT_ID,
        merchant_name="Tesseract Demo Store",
        capabilities=[
            UCPCapability(name="catalog_search", version="1.0"),
            UCPCapability(name="cart", version="1.0"),
            UCPCapability(name="checkout", version="1.0"),
            UCPCapability(name="order_management", version="1.0"),
            UCPCapability(name="ap2_mandate_verification", version="1.0"),
        ],
        checkout_url=f"{os.getenv('MERCHANT_BASE_URL', 'http://localhost:8080')}/ucp/checkout",
    )


# ── Catalog ────────────────────────────────────────────────────
@app.post("/ucp/catalog/search", response_model=CatalogSearchResponse)
async def catalog_search(req: CatalogSearchRequest):
    """UCP catalog search — agent discovers products here."""
    products = search_products(req.query, req.max_results)
    return CatalogSearchResponse(products=products, total=len(products))


# ── Cart ───────────────────────────────────────────────────────
@app.post("/ucp/cart", response_model=CartResponse)
async def create_cart(req: CreateCartRequest):
    """Build a UCP cart. Agent provides line items."""
    enriched_items: list[CartItem] = []
    for item in req.items:
        product = get_product(item.product_id)
        if not product:
            raise HTTPException(status_code=404, detail=f"Product {item.product_id} not found")
        if not product.available:
            raise HTTPException(status_code=409, detail=f"Product {item.product_id} is unavailable")
        enriched_items.append(CartItem(
            product_id=product.id,
            product_name=product.name,
            quantity=item.quantity,
            unit_price_usd=product.price_usd,
        ))

    subtotal = sum(i.unit_price_usd * i.quantity for i in enriched_items)
    tax = round(subtotal * 0.08, 2)  # 8% mock tax
    cart = CartResponse(
        cart_id=str(uuid.uuid4()),
        items=enriched_items,
        subtotal_usd=round(subtotal, 2),
        tax_usd=tax,
        total_usd=round(subtotal + tax, 2),
    )
    _carts[cart.cart_id] = cart
    return cart


# ── Checkout ───────────────────────────────────────────────────
@app.post("/ucp/checkout", response_model=OrderResponse)
async def checkout(req: CheckoutRequest):
    """
    UCP checkout — verifies AP2 Intent + Cart Mandates before confirming.
    This is the critical trust gate: no valid mandates = no order.
    """
    cart = _carts.get(req.cart_id)
    if not cart:
        raise HTTPException(status_code=404, detail="Cart not found")

    # ── AP2 Mandate Verification ───────────────────────────────
    intent_ok, intent_msg = verify_mandate(req.intent_mandate, expected_type="IntentMandate")
    if not intent_ok:
        raise HTTPException(status_code=403, detail=f"Intent Mandate invalid: {intent_msg}")

    cart_ok, cart_msg = verify_mandate(req.cart_mandate, expected_type="CartMandate")
    if not cart_ok:
        raise HTTPException(status_code=403, detail=f"Cart Mandate invalid: {cart_msg}")

    # ── Cross-check cart_id in Cart Mandate matches request ────
    if req.cart_mandate.get("credentialSubject", {}).get("cart_id") != req.cart_id:
        raise HTTPException(status_code=400, detail="Cart Mandate cart_id mismatch")

    order = OrderResponse(
        order_id=str(uuid.uuid4()),
        status="confirmed",
        cart_id=req.cart_id,
        total_usd=cart.total_usd,
        message="Order confirmed. AP2 mandates verified. Transaction is non-repudiable.",
    )
    _orders[order.order_id] = order
    return order


# ── Order Status ───────────────────────────────────────────────
@app.get("/ucp/order/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str):
    """UCP order management — fetch order status post-checkout."""
    order = _orders.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
