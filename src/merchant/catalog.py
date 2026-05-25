"""Mock product catalog."""
from src.merchant.models import Product

MOCK_CATALOG: list[Product] = [
    Product(id="prod-001", name="Wireless Noise-Cancelling Headphones",
            description="Premium over-ear headphones, 30hr battery, ANC.",
            price_usd=149.99, category="Electronics"),
    Product(id="prod-002", name="Mechanical Keyboard (TKL)",
            description="Tenkeyless, Cherry MX Brown.",
            price_usd=89.99, category="Electronics"),
    Product(id="prod-003", name="Ergonomic Standing Desk Mat",
            description="Anti-fatigue, 3/4 inch, 30x20in.",
            price_usd=39.99, category="Office"),
    Product(id="prod-004", name="USB-C 100W GaN Charger",
            description="4-port, 100W total, travel-friendly.",
            price_usd=49.99, category="Electronics"),
    Product(id="prod-005", name="Bamboo Desk Organiser",
            description="Sustainable, 6 compartments.",
            price_usd=29.99, category="Office"),
]


def search_products(query: str, max_results: int = 5) -> list[Product]:
    q = query.lower()
    matched = [p for p in MOCK_CATALOG
               if q in p.name.lower() or q in p.category.lower() or q in p.description.lower()]
    return (matched or MOCK_CATALOG)[:max_results]


def get_product(product_id: str) -> Product | None:
    return next((p for p in MOCK_CATALOG if p.id == product_id), None)
