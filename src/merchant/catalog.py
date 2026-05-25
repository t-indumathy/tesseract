"""Mock product catalog for the UCP merchant server."""
from src.merchant.models import Product

MOCK_CATALOG: list[Product] = [
    Product(
        id="prod-001",
        name="Wireless Noise-Cancelling Headphones",
        description="Premium over-ear headphones with 30hr battery and ANC.",
        price_usd=149.99,
        category="Electronics",
    ),
    Product(
        id="prod-002",
        name="Mechanical Keyboard (TKL)",
        description="Tenkeyless mechanical keyboard, Cherry MX Brown switches.",
        price_usd=89.99,
        category="Electronics",
    ),
    Product(
        id="prod-003",
        name="Ergonomic Standing Desk Mat",
        description="Anti-fatigue mat, 3/4 inch thick, 30x20 inches.",
        price_usd=39.99,
        category="Office",
    ),
    Product(
        id="prod-004",
        name="USB-C 100W GaN Charger",
        description="4-port GaN charger, 100W total output, travel-friendly.",
        price_usd=49.99,
        category="Electronics",
    ),
    Product(
        id="prod-005",
        name="Bamboo Desk Organiser",
        description="Sustainable bamboo organiser with 6 compartments.",
        price_usd=29.99,
        category="Office",
    ),
]


def search_products(query: str, max_results: int = 5) -> list[Product]:
    """Simple keyword search over the mock catalog."""
    query_lower = query.lower()
    matched = [
        p for p in MOCK_CATALOG
        if query_lower in p.name.lower()
        or query_lower in p.description.lower()
        or query_lower in p.category.lower()
    ]
    # If no match, return all (demo convenience)
    if not matched:
        matched = MOCK_CATALOG
    return matched[:max_results]


def get_product(product_id: str) -> Product | None:
    return next((p for p in MOCK_CATALOG if p.id == product_id), None)
