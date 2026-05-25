# Copyright 2025 Google LLC  (Apache-2.0)
# Mirrors: google-agentic-commerce/AP2 — code/samples/python/src/roles/merchant_agent/storage.py
"""In-memory cart + order store for the Tesseract merchant server.

The upstream merchant_agent/storage.py uses the same shape. We add an
`orders` store so we can surface order status after checkout.
"""
from __future__ import annotations
from typing import Any

# cart_id → { amount, currency, item_label, risk_data? }
_carts: dict[str, dict[str, Any]] = {}

# order_id → { cart_id, status, total, transaction_id }
_orders: dict[str, dict[str, Any]] = {}


# ── Cart helpers ───────────────────────────────────────────────────

def save_cart(cart_id: str, data: dict[str, Any]) -> None:
    _carts[cart_id] = data


def get_cart_data(cart_id: str) -> dict[str, Any] | None:
    """Named to match upstream storage.py API exactly."""
    return _carts.get(cart_id)


def get_risk_data(context_id: str) -> str:
    """Stub — upstream attaches browser/device signals here."""
    return f"risk:context={context_id}"


# ── Order helpers ──────────────────────────────────────────────────

def save_order(order_id: str, data: dict[str, Any]) -> None:
    _orders[order_id] = data


def get_order(order_id: str) -> dict[str, Any] | None:
    return _orders.get(order_id)
