"""UCP Pydantic models — aligned with UCP specification primitives."""
from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field
import uuid


# ── Capability Manifest ────────────────────────────────────────
class UCPCapability(BaseModel):
    name: str
    version: str
    supported: bool = True


class UCPManifest(BaseModel):
    merchant_id: str
    merchant_name: str
    ucp_version: str = "1.0"
    capabilities: list[UCPCapability]
    checkout_url: str
    ap2_supported: bool = True


# ── Catalog ────────────────────────────────────────────────────
class Product(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str
    price_usd: float
    currency: str = "USD"
    available: bool = True
    category: str
    image_url: str = ""


class CatalogSearchRequest(BaseModel):
    query: str
    max_results: int = 5


class CatalogSearchResponse(BaseModel):
    products: list[Product]
    total: int


# ── Cart ───────────────────────────────────────────────────────
class CartItem(BaseModel):
    product_id: str
    product_name: str
    quantity: int = 1
    unit_price_usd: float


class CreateCartRequest(BaseModel):
    items: list[CartItem]
    buyer_agent_id: str


class CartResponse(BaseModel):
    cart_id: str
    items: list[CartItem]
    subtotal_usd: float
    tax_usd: float
    total_usd: float
    currency: str = "USD"


# ── Checkout ───────────────────────────────────────────────────
class CheckoutRequest(BaseModel):
    cart_id: str
    intent_mandate: dict[str, Any]  # AP2 Intent Mandate VC
    cart_mandate: dict[str, Any]    # AP2 Cart Mandate VC
    payment_token: str = "mock-payment-token"


class OrderResponse(BaseModel):
    order_id: str
    status: str  # "confirmed" | "pending" | "failed"
    cart_id: str
    total_usd: float
    message: str
