"""Pydantic models shaped exactly to the UCP 2026-04-08 spec.

Key spec refs:
  - Profile: https://ucp.dev/2026-04-08/specification/overview/#profile-structure
  - Checkout: https://ucp.dev/2026-04-08/specification/checkout
  - Capability names: reverse-domain format, e.g. dev.ucp.shopping.checkout
"""
from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field
import uuid


# ---------------------------------------------------------------------------
# UCP Profile (/.well-known/ucp)
# Ref: https://ucp.dev/2026-04-08/specification/overview/#business-profile
# ---------------------------------------------------------------------------

class UCPServiceBinding(BaseModel):
    """Single transport binding for a service."""
    version: str = "2026-04-08"
    spec: str
    transport: str  # "rest" | "mcp" | "a2a" | "embedded"
    endpoint: str | None = None
    schema_url: str | None = Field(None, alias="schema")

    model_config = {"populate_by_name": True}


class UCPCapabilityEntry(BaseModel):
    """Single capability version entry in the profile."""
    version: str = "2026-04-08"
    spec: str
    schema_url: str = Field(alias="schema")
    extends: str | list[str] | None = None
    config: dict[str, Any] | None = None

    model_config = {"populate_by_name": True}


class UCPProfile(BaseModel):
    """The full /.well-known/ucp response."""
    ucp: UCPProfileBody


class UCPProfileBody(BaseModel):
    version: str = "2026-04-08"
    # service name → list of transport bindings
    services: dict[str, list[UCPServiceBinding]]
    # capability name → list of UCPCapabilityEntry
    capabilities: dict[str, list[UCPCapabilityEntry]]
    payment_handlers: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# UCP Response envelope — every response MUST carry this
# Ref: https://ucp.dev/2026-04-08/specification/overview/#capability-declaration-in-responses
# ---------------------------------------------------------------------------

class UCPResponseCapabilityVersion(BaseModel):
    version: str = "2026-04-08"


class UCPResponseEnvelope(BaseModel):
    """The `ucp` block that MUST appear in every merchant response."""
    version: str = "2026-04-08"
    capabilities: dict[str, list[UCPResponseCapabilityVersion]]
    status: str = "ok"


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

class Product(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str
    price_usd: float
    currency: str = "USD"
    available: bool = True
    category: str


class CatalogSearchRequest(BaseModel):
    query: str
    max_results: int = 5


class CatalogSearchResponse(BaseModel):
    ucp: UCPResponseEnvelope
    products: list[Product]
    total: int


# ---------------------------------------------------------------------------
# Cart  (dev.ucp.shopping.cart)
# Ref: https://ucp.dev/2026-04-08/specification/cart
# ---------------------------------------------------------------------------

class LineItem(BaseModel):
    """UCP spec uses 'line_items', not 'items'."""
    product_id: str
    product_name: str
    quantity: int = 1
    unit_amount: int  # minor units (cents), per spec: "Amounts format: Minor units"
    total_amount: int


class CreateCartRequest(BaseModel):
    line_items: list[dict[str, Any]]  # [{ product_id, quantity }]
    buyer_agent_id: str


class CartTotals(BaseModel):
    subtotal: int   # cents
    tax: int
    total: int
    currency: str = "USD"


class CartResponse(BaseModel):
    ucp: UCPResponseEnvelope
    id: str  # spec uses `id` not `cart_id`
    line_items: list[LineItem]
    totals: CartTotals


# ---------------------------------------------------------------------------
# Checkout  (dev.ucp.shopping.checkout)
# Ref: https://ucp.dev/2026-04-08/specification/checkout
# ---------------------------------------------------------------------------

class AP2MandatePayload(BaseModel):
    """Container for AP2 Verifiable Credentials in the checkout request."""
    intent_mandate: dict[str, Any]
    cart_mandate: dict[str, Any]


class CreateCheckoutSessionRequest(BaseModel):
    """
    POST /checkout-sessions

    Includes the AP2 mandates under the dev.ucp.shopping.ap2_mandate extension.
    The UCP-Agent header (RFC 8941) must be set by the client — enforced in server.py.
    """
    cart_id: str
    ap2: AP2MandatePayload | None = None  # required if ap2_mandate capability is active
    payment_token: str = "mock-payment-token"


class CheckoutSessionResponse(BaseModel):
    ucp: UCPResponseEnvelope
    id: str          # checkout session id
    status: str      # "completed" | "pending" | "failed"
    cart_id: str
    total_amount: int  # cents
    currency: str = "USD"
    message: str
