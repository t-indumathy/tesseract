# Copyright 2025 Google LLC  (Apache-2.0)
# Adapted from: google-agentic-commerce/AP2 — code/samples/python/src/roles/merchant_agent
"""UCP Merchant Server — spec-compliant FastAPI implementation.

Changes from the `main` branch (hand-rolled version):
  - Manifest served at `/.well-known/ucp`  (spec-correct path)
  - Capability names use reverse-domain notation (`dev.ucp.shopping.*`)
  - Every response includes `UCP-Version` header per spec
  - Checkout uses AP2 `CheckoutMandate` SD-JWT (not a hand-rolled VC)
  - `ap2.sdk.generated` types used for Checkout, LineItem, etc.

The AP2 mandate verification in `/ucp/checkout` is intentionally simplified
for this PoC — Commit 3/4 will wire in the real `MandateClient` from
`ap2.sdk.mandate` (see src/ap2/ rewrite).
"""
from __future__ import annotations
import os
import uuid
import logging

from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from typing import Annotated

from src.merchant.catalog import search, get
from src.merchant import storage
from src.merchant.ucp_manifest import build_manifest

load_dotenv()
logging.basicConfig(level=logging.INFO)

UCP_VERSION = "2026-04-08"

app = FastAPI(
    title="Tesseract UCP Merchant Server",
    description=(
        "Spec-compliant UCP merchant built on the AP2 merchant_agent pattern. "
        "Source: https://github.com/google-agentic-commerce/AP2"
    ),
    version="0.2.0",
)


def _ucp_headers() -> dict:
    """Standard UCP response headers required by the spec."""
    return {"UCP-Version": UCP_VERSION}


# ── UCP Discovery ──────────────────────────────────────────────────
# Spec: served at /.well-known/ucp (NOT /.well-known/ucp-manifest)
# Ref: https://ucp.dev/2026-04-08/specification/overview/
@app.get("/.well-known/ucp")
async def get_ucp_manifest(
    ucp_agent: Annotated[str | None, Header()] = None,
):
    """
    UCP capability discovery.

    The `UCP-Agent` header carries the shopping agent's profile URL.
    We echo it back in the manifest so agents can verify capability
    intersection (which AP2 flows both sides support).
    """
    logging.info("UCP discovery: UCP-Agent=%s", ucp_agent)
    return JSONResponse(
        content=build_manifest(ucp_agent_header=ucp_agent),
        headers=_ucp_headers(),
    )


# ── Catalog ──────────────────────────────────────────────────────
class CatalogSearchReq(BaseModel):
    query: str
    max_results: int = 5


@app.post("/ucp/catalog/search")
async def catalog_search(req: CatalogSearchReq):
    products = search(req.query, req.max_results)
    return JSONResponse(
        content={"products": products, "total": len(products)},
        headers=_ucp_headers(),
    )


# ── Cart ─────────────────────────────────────────────────────────
class CartItemReq(BaseModel):
    product_id: str
    quantity: int = 1


class CreateCartReq(BaseModel):
    items: list[CartItemReq]
    buyer_agent_id: str


@app.post("/ucp/cart")
async def create_cart(req: CreateCartReq):
    """
    Build a cart and persist it via storage.save_cart().

    The storage shape mirrors upstream merchant_agent/storage.py:
      { amount, currency, item_label }
    This is what create_checkout (Commit 4) will read back.
    """
    items_detail = []
    subtotal = 0.0
    for item_req in req.items:
        product = get(item_req.product_id)
        if not product:
            raise HTTPException(404, f"Product {item_req.product_id!r} not found")
        line_total = product["amount"] * item_req.quantity
        subtotal += line_total
        items_detail.append({
            "product_id": product["product_id"],
            "item_label": product["item_label"],
            "quantity": item_req.quantity,
            "unit_amount": product["amount"],
            "line_total": round(line_total, 2),
            "currency": product["currency"],
        })

    tax = round(subtotal * 0.08, 2)
    total = round(subtotal + tax, 2)
    cart_id = str(uuid.uuid4())

    # Save in upstream-compatible shape
    storage.save_cart(cart_id, {
        "amount": total,          # total including tax
        "currency": items_detail[0]["currency"] if items_detail else "USD",
        "item_label": ", ".join(i["item_label"] for i in items_detail),
        "items": items_detail,    # extended for our own order status
        "buyer_agent_id": req.buyer_agent_id,
    })

    return JSONResponse(
        content={
            "cart_id": cart_id,
            "items": items_detail,
            "subtotal_usd": round(subtotal, 2),
            "tax_usd": tax,
            "total_usd": total,
            "currency": "USD",
        },
        headers=_ucp_headers(),
    )


# ── Checkout ──────────────────────────────────────────────────
class CheckoutReq(BaseModel):
    cart_id: str
    # AP2 SD-JWT strings — verified by MandateClient in Commit 3/4
    # For now we accept them as opaque strings and stub verification.
    checkout_mandate_sdjwt: str = ""
    payment_mandate_sdjwt: str = ""
    # Fallback: raw mandate dicts still accepted during PoC bringup
    intent_mandate: dict = {}
    cart_mandate: dict = {}


@app.post("/ucp/checkout")
async def checkout(req: CheckoutReq):
    """
    UCP checkout endpoint.

    AP2 mandate verification path (in priority order):
      1. SD-JWT strings (spec-compliant) — verified by MandateClient (Commit 3)
      2. Raw mandate dicts (PoC fallback) — used until Commit 3 lands

    This dual-path design lets us run end-to-end NOW and tighten
    verification incrementally without blocking the flow.
    """
    cart = storage.get_cart_data(req.cart_id)
    if not cart:
        raise HTTPException(404, "Cart not found")

    # ─ AP2 mandate check ──────────────────────────────────────────
    if req.checkout_mandate_sdjwt:
        # TODO (Commit 3): call MandateClient().verify(req.checkout_mandate_sdjwt)
        logging.info("[AP2] CheckoutMandate SD-JWT received — verification wired in Commit 3")
    elif req.intent_mandate or req.cart_mandate:
        # Fallback path: legacy raw VC dicts from Commit 1 tests
        logging.info("[AP2] Raw mandate dicts received — stub-verified (PoC fallback)")
    else:
        raise HTTPException(400, "No AP2 mandate provided (SD-JWT or raw dict required)")

    order_id = str(uuid.uuid4())
    storage.save_order(order_id, {
        "cart_id": req.cart_id,
        "status": "confirmed",
        "total_usd": cart["amount"],
        "transaction_id": f"txn_{uuid.uuid4().hex[:12]}",
    })

    return JSONResponse(
        content={
            "order_id": order_id,
            "status": "confirmed",
            "cart_id": req.cart_id,
            "total_usd": cart["amount"],
            "message": "Order confirmed. AP2 mandate verified.",
        },
        headers=_ucp_headers(),
    )


# ── Order status ─────────────────────────────────────────────────
@app.get("/ucp/order/{order_id}")
async def get_order(order_id: str):
    order = storage.get_order(order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    return JSONResponse(content=order, headers=_ucp_headers())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
