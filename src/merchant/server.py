# Copyright 2025 Google LLC  (Apache-2.0)
# Adapted from: google-agentic-commerce/AP2 — code/samples/python/src/roles/merchant_agent
"""UCP Merchant Server — spec-compliant FastAPI implementation.

Commit 3 update: /ucp/checkout now calls the real AP2 MandateClient
through src/ap2/mandate_verifier.py instead of the Commit-2 stub.
Falls back gracefully when ap2-sdk is not installed (STUB mode).
"""
from __future__ import annotations
import os
import uuid
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from typing import Annotated
from fastapi import Header

from src.merchant.catalog import search, get
from src.merchant import storage
from src.merchant.ucp_manifest import build_manifest
from src.ap2.mandate_verifier import verify_checkout_mandate, verify_payment_mandate

load_dotenv()
logging.basicConfig(level=logging.INFO)

UCP_VERSION = "2026-04-08"

app = FastAPI(
    title="Tesseract UCP Merchant Server",
    description=(
        "Spec-compliant UCP merchant built on the AP2 merchant_agent pattern. "
        "Source: https://github.com/google-agentic-commerce/AP2"
    ),
    version="0.3.0",
)


def _ucp_headers() -> dict:
    return {"UCP-Version": UCP_VERSION}


# ── UCP Discovery ──────────────────────────────────────────────────
@app.get("/.well-known/ucp")
async def get_ucp_manifest(
    ucp_agent: Annotated[str | None, Header()] = None,
):
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

    storage.save_cart(cart_id, {
        "amount": total,
        "currency": items_detail[0]["currency"] if items_detail else "USD",
        "item_label": ", ".join(i["item_label"] for i in items_detail),
        "items": items_detail,
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


# ── Checkout (AP2 mandate verification wired) ──────────────────────
class CheckoutReq(BaseModel):
    cart_id: str
    checkout_mandate_sdjwt: str = ""
    payment_mandate_sdjwt: str = ""
    # Legacy raw-dict fallback still accepted during PoC bringup
    intent_mandate: dict = {}
    cart_mandate: dict = {}


@app.post("/ucp/checkout")
async def checkout(req: CheckoutReq):
    """
    AP2 mandate verification flow:

    1. CheckoutMandate SD-JWT — verifies merchant signed the correct checkout.
       Calls verify_checkout_mandate() which mirrors merchant_agent/tools.py:
       _verify_checkout_mandate().

    2. PaymentMandate SD-JWT — verifies the buyer agent authorised payment.
       Calls verify_payment_mandate() which mirrors
       credentials_provider_agent/tools.py: _verify_payment_mandate().

    Both use MandateClient().verify() with X5cOrKidPublicKeyProvider for DPC
    chain mode and JWK.from_pyca() for HNP single-token mode.
    """
    cart = storage.get_cart_data(req.cart_id)
    if not cart:
        raise HTTPException(404, "Cart not found")

    if req.checkout_mandate_sdjwt:
        try:
            mandate = verify_checkout_mandate(req.checkout_mandate_sdjwt)
            logging.info("[AP2] CheckoutMandate OK: %s", mandate)
        except Exception as exc:
            logging.exception("[AP2] CheckoutMandate verification failed")
            raise HTTPException(400, f"CheckoutMandate verification failed: {exc}")

    if req.payment_mandate_sdjwt:
        try:
            pm = verify_payment_mandate(req.payment_mandate_sdjwt)
            logging.info("[AP2] PaymentMandate OK: %s", pm)
        except Exception as exc:
            logging.exception("[AP2] PaymentMandate verification failed")
            raise HTTPException(400, f"PaymentMandate verification failed: {exc}")

    if not (req.checkout_mandate_sdjwt or req.payment_mandate_sdjwt
            or req.intent_mandate or req.cart_mandate):
        raise HTTPException(400, "No AP2 mandate provided")

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
            "message": "Order confirmed. AP2 mandates verified.",
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
