# Copyright 2025 Google LLC  (Apache-2.0)
# Adapted from: google-agentic-commerce/AP2 — code/samples/python/src/roles/merchant_agent
"""Mock product catalog used by the Tesseract merchant agent."""
from __future__ import annotations

# Each entry maps product_id → cart-storage dict that mirrors what
# merchant_agent/storage.py keeps: { amount, currency, item_label }.
# We extend it with display metadata (description, category) for the
# shopping-agent's search results.

CATALOG: dict[str, dict] = {
    "prod-001": {
        "item_label": "Wireless Noise-Cancelling Headphones",
        "description": "Premium over-ear ANC headphones, 30 hr battery.",
        "category": "Electronics",
        "amount": 149.99,
        "currency": "USD",
    },
    "prod-002": {
        "item_label": "Mechanical Keyboard (TKL)",
        "description": "Tenkeyless, Cherry MX Brown switches.",
        "category": "Electronics",
        "amount": 89.99,
        "currency": "USD",
    },
    "prod-003": {
        "item_label": "Ergonomic Standing Desk Mat",
        "description": "Anti-fatigue mat, 3/4 inch thick, 30x20 in.",
        "category": "Office",
        "amount": 39.99,
        "currency": "USD",
    },
    "prod-004": {
        "item_label": "USB-C 100W GaN Charger",
        "description": "4-port GaN, 100 W total, travel-friendly.",
        "category": "Electronics",
        "amount": 49.99,
        "currency": "USD",
    },
    "prod-005": {
        "item_label": "Bamboo Desk Organiser",
        "description": "Sustainable bamboo, 6 compartments.",
        "category": "Office",
        "amount": 29.99,
        "currency": "USD",
    },
}


def search(query: str, max_results: int = 5) -> list[dict]:
    """Keyword search over the catalog. Returns list of product dicts."""
    q = query.lower()
    hits = [
        {"product_id": pid, **data}
        for pid, data in CATALOG.items()
        if q in data["item_label"].lower()
        or q in data["description"].lower()
        or q in data["category"].lower()
    ]
    return (hits or list({"product_id": pid, **d} for pid, d in CATALOG.items()))[:max_results]


def get(product_id: str) -> dict | None:
    """Fetch a single product by id."""
    data = CATALOG.get(product_id)
    return {"product_id": product_id, **data} if data else None
