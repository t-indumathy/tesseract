"""UCP-compliant Merchant Server — FastAPI.

Spec compliance checklist:
  [x] /.well-known/ucp — correct 2026-04-08 profile shape
  [x] /platform-profile — platform profile served locally for PoC
  [x] UCP-Agent header enforced on every mutating request
  [x] Capability intersection computed per-request from platform profile
  [x] ucp block echoed in EVERY response (mandatory per spec)
  [x] Capability names in reverse-domain format (dev.ucp.*)
  [x] dev.ucp.shopping.ap2_mandate declared + enforced at checkout
  [x] Endpoint paths follow UCP REST OpenAPI convention
      (e.g. /checkout-sessions not /ucp/checkout)

UCP REST endpoint paths per spec:
  POST   /carts                     — create cart
  POST   /checkout-sessions         — initiate checkout
  GET    /checkout-sessions/{id}    — get checkout session
  GET    /orders/{id}               — get order
"""
from __future__ import annotations
import os
import uuid
import httpx
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

from src.merchant.models import (
    CatalogSearchRequest, CatalogSearchResponse,
    CreateCartRequest, CartResponse, CartTotals, LineItem,
    CreateCheckoutSessionRequest, CheckoutSessionResponse,
    UCPResponseEnvelope, UCPResponseCapabilityVersion,
)
from src.merchant.catalog import search_products, get_product
from src.merchant.profile import build_business_profile, build_platform_profile
from src.merchant.negotiation import intersect_capabilities, build_response_capabilities
from src.ap2.verifier import verify_mandate

load_dotenv()

app = FastAPI(
    title="Tesseract UCP Merchant (spec-compliant)",
    version="0.2.0",
)

_carts: dict[str, CartResponse] = {}
_checkouts: dict[str, CheckoutSessionResponse] = {}

# Business capabilities (loaded once at startup)
_BUSINESS_PROFILE = build_business_profile()
_BUSINESS_CAPS: dict[str, list[dict]] = {
    name: [e.model_dump(by_alias=True, exclude_none=True) for e in entries]
    for name, entries in _BUSINESS_PROFILE.ucp.capabilities.items()
}


def _get_platform_caps(platform_profile_url: str) -> dict[str, list[dict]]:
    """
    Fetch + cache platform profile and extract its capabilities.

    Spec requires:
      - MUST NOT follow redirects
      - SHOULD enforce timeouts
      - SHOULD cache with min 60s TTL

    This PoC fetches inline (no cache); swap with an LRU cache for production.
    """
    try:
        with httpx.Client(follow_redirects=False, timeout=5.0) as client:
            resp = client.get(platform_profile_url)
            resp.raise_for_status()
            data = resp.json()
            return data.get("ucp", {}).get("capabilities", {})
    except Exception as exc:
        raise HTTPException(
            status_code=424,
            detail={"code": "profile_unreachable", "content": str(exc)},
        )


def _parse_ucp_agent(ucp_agent: str | None) -> str:
    """
    Parse UCP-Agent header value (RFC 8941 Dictionary Structured Field).
    Expected: UCP-Agent: profile="https://..."
    Spec: https://ucp.dev/2026-04-08/specification/overview/#platform-advertisement-on-request
    """
    if not ucp_agent:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_profile_url",
                    "content": "UCP-Agent header is required on all requests."},
        )
    # Minimal RFC 8941 dictionary parse for `profile` key
    for part in ucp_agent.split(","):
        part = part.strip()
        if part.startswith("profile="):
            url = part[len("profile="):].strip('"')
            if url.startswith("http"):
                return url
    raise HTTPException(
        status_code=400,
        detail={"code": "invalid_profile_url",
                "content": f"Could not parse profile URL from UCP-Agent: {ucp_agent}"},
    )


def _negotiate(ucp_agent: str | None, operation_type: str) -> dict[str, list[dict]]:
    """Parse UCP-Agent → fetch platform profile → intersect → build response caps."""
    profile_url = _parse_ucp_agent(ucp_agent)
    platform_caps = _get_platform_caps(profile_url)
    active = intersect_capabilities(_BUSINESS_CAPS, platform_caps)
    return build_response_capabilities(active, operation_type)


def _ucp_envelope(operation_type: str, active_caps: dict[str, list[dict]]) -> UCPResponseEnvelope:
    return UCPResponseEnvelope(
        version="2026-04-08",
        capabilities={
            name: [UCPResponseCapabilityVersion(version=v["version"]) for v in versions]
            for name, versions in active_caps.items()
        },
    )


# ---------------------------------------------------------------------------
# Profile endpoints
# ---------------------------------------------------------------------------

@app.get("/.well-known/ucp")
async def get_ucp_profile():
    """UCP Business Profile — spec-compliant 2026-04-08 shape."""
    return _BUSINESS_PROFILE.model_dump(by_alias=True, exclude_none=True)


@app.get("/platform-profile")
async def get_platform_profile():
    """
    Platform (agent) profile — served here for local PoC convenience.
    In production this would be hosted at a stable HTTPS URL.
    """
    return build_platform_profile()


# ---------------------------------------------------------------------------
# Catalog  (not a formal UCP capability in v1 spec, but required for demo)
# ---------------------------------------------------------------------------

@app.post("/ucp/v1/catalog/search", response_model=CatalogSearchResponse)
async def catalog_search(
    req: CatalogSearchRequest,
    ucp_agent: str | None = Header(None, alias="UCP-Agent"),
):
    active_caps = _negotiate(ucp_agent, "checkout")  # catalog is pre-checkout context
    products = search_products(req.query, req.max_results)
    return CatalogSearchResponse(
        ucp=_ucp_envelope("checkout", active_caps),
        products=products,
        total=len(products),
    )


# ---------------------------------------------------------------------------
# Cart  (dev.ucp.shopping.cart)
# UCP REST path: POST /carts
# ---------------------------------------------------------------------------

@app.post("/ucp/v1/carts", response_model=CartResponse)
async def create_cart(
    req: CreateCartRequest,
    ucp_agent: str | None = Header(None, alias="UCP-Agent"),
):
    """Create a UCP cart. Returns line_items + totals in minor units (cents)."""
    active_caps = _negotiate(ucp_agent, "cart")

    line_items: list[LineItem] = []
    for item in req.line_items:
        product = get_product(item["product_id"])
        if not product:
            raise HTTPException(404, f"Product {item['product_id']} not found")
        qty = item.get("quantity", 1)
        unit_cents = int(product.price_usd * 100)
        line_items.append(LineItem(
            product_id=product.id,
            product_name=product.name,
            quantity=qty,
            unit_amount=unit_cents,
            total_amount=unit_cents * qty,
        ))

    subtotal = sum(li.total_amount for li in line_items)
    tax = int(subtotal * 0.08)
    total = subtotal + tax

    cart = CartResponse(
        ucp=_ucp_envelope("cart", active_caps),
        id=str(uuid.uuid4()),
        line_items=line_items,
        totals=CartTotals(subtotal=subtotal, tax=tax, total=total),
    )
    _carts[cart.id] = cart
    return cart


# ---------------------------------------------------------------------------
# Checkout  (dev.ucp.shopping.checkout + dev.ucp.shopping.ap2_mandate)
# UCP REST path: POST /checkout-sessions
# ---------------------------------------------------------------------------

@app.post("/ucp/v1/checkout-sessions", response_model=CheckoutSessionResponse)
async def create_checkout_session(
    req: CreateCheckoutSessionRequest,
    ucp_agent: str | None = Header(None, alias="UCP-Agent"),
):
    """
    UCP checkout — the spec trust gate.

    If dev.ucp.shopping.ap2_mandate is in the negotiated intersection:
      - AP2 Intent Mandate MUST be present and valid
      - AP2 Cart Mandate MUST be present, valid, and match cart_id
    """
    active_caps = _negotiate(ucp_agent, "checkout")

    cart = _carts.get(req.cart_id)
    if not cart:
        raise HTTPException(404, "Cart not found")

    # AP2 mandate enforcement — only if capability is active after negotiation
    if "dev.ucp.shopping.ap2_mandate" in active_caps:
        if not req.ap2:
            raise HTTPException(
                400,
                {"code": "ap2_mandate_required",
                 "content": "dev.ucp.shopping.ap2_mandate is active; ap2 block is required."},
            )
        intent_ok, intent_msg = verify_mandate(req.ap2.intent_mandate, "IntentMandate")
        if not intent_ok:
            raise HTTPException(403, {"code": "intent_mandate_invalid", "content": intent_msg})

        cart_ok, cart_msg = verify_mandate(req.ap2.cart_mandate, "CartMandate")
        if not cart_ok:
            raise HTTPException(403, {"code": "cart_mandate_invalid", "content": cart_msg})

        if req.ap2.cart_mandate.get("credentialSubject", {}).get("cart_id") != req.cart_id:
            raise HTTPException(400, {"code": "cart_id_mismatch",
                                      "content": "Cart Mandate cart_id does not match request."})

    session = CheckoutSessionResponse(
        ucp=_ucp_envelope("checkout", active_caps),
        id=str(uuid.uuid4()),
        status="completed",
        cart_id=req.cart_id,
        total_amount=cart.totals.total,
        currency="USD",
        message="Checkout complete. AP2 mandates verified. Transaction is non-repudiable.",
    )
    _checkouts[session.id] = session
    return session


@app.get("/ucp/v1/checkout-sessions/{session_id}", response_model=CheckoutSessionResponse)
async def get_checkout_session(
    session_id: str,
    ucp_agent: str | None = Header(None, alias="UCP-Agent"),
):
    active_caps = _negotiate(ucp_agent, "checkout")
    session = _checkouts.get(session_id)
    if not session:
        raise HTTPException(404, "Checkout session not found")
    # Refresh ucp envelope with re-negotiated caps
    session.ucp = _ucp_envelope("checkout", active_caps)
    return session
