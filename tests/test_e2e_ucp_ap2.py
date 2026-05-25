# Copyright 2025 Google LLC  (Apache-2.0)
# End-to-end PoC test suite for Tesseract UCP + AP2 flow.
# Mirrors the flow exercised by the AP2 sample shopping_agent:
#   google-agentic-commerce/AP2/code/samples/python/src/roles/shopping_agent
"""
Test sequence (mirrors the real AP2 shopping agent flow):

  1. UCP Discovery     GET  /.well-known/ucp
  2. Catalog Search    POST /ucp/catalog/search
  3. Cart Creation     POST /ucp/cart
  4. Checkout (stub)   POST /ucp/checkout  (raw mandate dicts — no ap2-sdk needed)
  5. Order Status      GET  /ucp/order/{order_id}
  6. Checkout (sdjwt)  POST /ucp/checkout  (AP2 SD-JWT path, graceful stub fallback)

All tests run without the ap2-sdk installed — mandate_verifier.py falls back
to STUB mode and the assertions remain valid.
"""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient

from src.merchant.server import app

client = TestClient(app)


# ─── helpers ──────────────────────────────────────────────────────────────

def _assert_ucp_header(response):
    """Every UCP endpoint must return UCP-Version header."""
    assert response.headers.get("ucp-version") == "2026-04-08", (
        f"Missing or wrong UCP-Version header: {dict(response.headers)}"
    )


# ─── Step 1: UCP Discovery ──────────────────────────────────────────────

class TestUCPDiscovery:
    def test_manifest_path(self):
        """Spec requires /.well-known/ucp (not ucp-manifest)."""
        r = client.get("/.well-known/ucp")
        assert r.status_code == 200
        _assert_ucp_header(r)

    def test_manifest_structure(self):
        r = client.get("/.well-known/ucp")
        body = r.json()
        assert "ucp" in body, "Top-level 'ucp' key required by spec"
        ucp = body["ucp"]
        assert ucp["version"] == "2026-04-08"
        assert "capabilities" in ucp
        assert "payment_handlers" in ucp

    def test_capability_names_are_reverse_domain(self):
        """Capability keys must use reverse-domain notation per UCP spec."""
        r = client.get("/.well-known/ucp")
        caps = r.json()["ucp"]["capabilities"]
        for key in caps:
            assert key.startswith("dev.ucp."), (
                f"Capability {key!r} must start with 'dev.ucp.' (reverse-domain)"
            )

    def test_ap2_payment_handler_advertised(self):
        r = client.get("/.well-known/ucp")
        ph = r.json()["ucp"]["payment_handlers"]
        assert "ap2" in ph
        assert ph["ap2"]["supported"] is True
        assert "HNP" in ph["ap2"]["flows"]
        assert "DPC" in ph["ap2"]["flows"]

    def test_ucp_agent_header_echoed(self):
        """UCP-Agent header must be echoed in manifest agent_profile."""
        agent_url = "https://shopping-agent.example.com"
        r = client.get(
            "/.well-known/ucp",
            headers={"ucp-agent": agent_url},
        )
        assert r.json()["ucp"]["agent_profile"] == agent_url


# ─── Step 2: Catalog Search ─────────────────────────────────────────────

class TestCatalogSearch:
    def test_keyword_search(self):
        r = client.post("/ucp/catalog/search", json={"query": "headphones"})
        assert r.status_code == 200
        _assert_ucp_header(r)
        body = r.json()
        assert body["total"] >= 1
        assert any(
            "headphones" in p["item_label"].lower() for p in body["products"]
        )

    def test_category_search(self):
        r = client.post("/ucp/catalog/search", json={"query": "office"})
        assert r.status_code == 200
        assert r.json()["total"] >= 1

    def test_empty_query_returns_all(self):
        r = client.post("/ucp/catalog/search", json={"query": ""})
        assert r.status_code == 200
        assert r.json()["total"] >= 1

    def test_max_results_respected(self):
        r = client.post(
            "/ucp/catalog/search", json={"query": "", "max_results": 2}
        )
        assert len(r.json()["products"]) <= 2


# ─── Step 3: Cart Creation ───────────────────────────────────────────────

@pytest.fixture(scope="module")
def cart_id():
    """Creates a cart once and shares the cart_id across checkout tests."""
    r = client.post("/ucp/cart", json={
        "items": [{"product_id": "prod-001", "quantity": 1}],
        "buyer_agent_id": "test-shopping-agent",
    })
    assert r.status_code == 200
    return r.json()["cart_id"]


class TestCartCreation:
    def test_create_cart(self):
        r = client.post("/ucp/cart", json={
            "items": [
                {"product_id": "prod-001", "quantity": 1},
                {"product_id": "prod-002", "quantity": 2},
            ],
            "buyer_agent_id": "test-agent",
        })
        assert r.status_code == 200
        _assert_ucp_header(r)
        body = r.json()
        assert "cart_id" in body
        assert body["total_usd"] > 0
        assert len(body["items"]) == 2

    def test_unknown_product_returns_404(self):
        r = client.post("/ucp/cart", json={
            "items": [{"product_id": "prod-999"}],
            "buyer_agent_id": "test-agent",
        })
        assert r.status_code == 404

    def test_tax_applied(self):
        """8% tax must be reflected in total_usd."""
        r = client.post("/ucp/cart", json={
            "items": [{"product_id": "prod-003", "quantity": 1}],
            "buyer_agent_id": "test-agent",
        })
        body = r.json()
        expected_total = round(39.99 * 1.08, 2)
        assert abs(body["total_usd"] - expected_total) < 0.01


# ─── Step 4 + 5: Checkout + Order Status ──────────────────────────────

class TestCheckout:
    def test_checkout_with_raw_mandate_dicts(self, cart_id):
        """
        Fallback path: raw mandate dicts (no ap2-sdk required).
        This is the PoC bringup path used until the real keys are provisioned.
        """
        r = client.post("/ucp/checkout", json={
            "cart_id": cart_id,
            "intent_mandate": {
                "buyer_agent_id": "test-shopping-agent",
                "action": "purchase",
            },
            "cart_mandate": {
                "cart_id": cart_id,
                "authorized_total_usd": 200.0,
            },
        })
        assert r.status_code == 200
        _assert_ucp_header(r)
        body = r.json()
        assert body["status"] == "confirmed"
        assert "order_id" in body
        assert body["cart_id"] == cart_id

    def test_checkout_with_sdjwt_stub(self, cart_id):
        """
        AP2 SD-JWT path: stub mode when ap2-sdk not installed.
        mandate_verifier.py logs a warning and returns {stub: True}.
        The checkout must still succeed (server does not fail on stub result).
        """
        r = client.post("/ucp/checkout", json={
            "cart_id": cart_id,
            # Fake SD-JWT structure — stub verifier accepts any non-empty string
            "checkout_mandate_sdjwt": "eyJhbGciOiJFUzI1NiJ9.stub.sig~disc~kbjwt",
            "payment_mandate_sdjwt":  "eyJhbGciOiJFUzI1NiJ9.stub.sig~disc~kbjwt",
        })
        # Stub mode: verifier returns {stub: True} — server confirms order
        assert r.status_code == 200
        assert r.json()["status"] == "confirmed"

    def test_checkout_no_mandate_returns_400(self, cart_id):
        r = client.post("/ucp/checkout", json={"cart_id": cart_id})
        assert r.status_code == 400

    def test_checkout_unknown_cart_returns_404(self):
        r = client.post("/ucp/checkout", json={
            "cart_id": "nonexistent-cart-id",
            "intent_mandate": {"action": "purchase"},
        })
        assert r.status_code == 404


class TestOrderStatus:
    def test_order_status_after_checkout(self, cart_id):
        # Checkout first to create an order
        checkout_r = client.post("/ucp/checkout", json={
            "cart_id": cart_id,
            "intent_mandate": {"action": "purchase"},
        })
        assert checkout_r.status_code == 200
        order_id = checkout_r.json()["order_id"]

        r = client.get(f"/ucp/order/{order_id}")
        assert r.status_code == 200
        _assert_ucp_header(r)
        body = r.json()
        assert body["status"] == "confirmed"
        assert body["cart_id"] == cart_id
        assert "transaction_id" in body

    def test_unknown_order_returns_404(self):
        r = client.get("/ucp/order/nonexistent-order-id")
        assert r.status_code == 404


# ─── Step 6: AP2 mandate verifier unit tests ───────────────────────────

class TestMandateVerifier:
    def test_stub_mode_payment_mandate(self):
        """When ap2-sdk absent, verify_payment_mandate returns stub dict."""
        from src.ap2.mandate_verifier import verify_payment_mandate, _AP2_AVAILABLE
        if _AP2_AVAILABLE:
            pytest.skip("ap2-sdk installed — real verification in effect")
        result = verify_payment_mandate("fake.sdjwt.string")
        assert result.get("stub") is True

    def test_stub_mode_checkout_mandate(self):
        from src.ap2.mandate_verifier import verify_checkout_mandate, _AP2_AVAILABLE
        if _AP2_AVAILABLE:
            pytest.skip("ap2-sdk installed — real verification in effect")
        result = verify_checkout_mandate("fake.sdjwt.string")
        assert result.get("stub") is True


# ─── Step 7: Credentials store unit tests ─────────────────────────────

class TestCredentialsStore:
    def test_get_shipping_address(self):
        from src.ap2.credentials import get_account_shipping_address
        addr = get_account_shipping_address("buyer@example.com")
        assert addr["country"] == "US"
        assert "street" in addr

    def test_get_payment_methods(self):
        from src.ap2.credentials import get_account_payment_methods
        methods = get_account_payment_methods("buyer@example.com")
        assert len(methods) >= 1
        assert all("alias" in m for m in methods)

    def test_create_token(self):
        from src.ap2.credentials import create_token
        token = create_token("buyer@example.com", "visa-4242")
        assert token.startswith("tok_")

    def test_unknown_account_raises(self):
        from src.ap2.credentials import get_account_shipping_address
        with pytest.raises(ValueError, match="Account not found"):
            get_account_shipping_address("nobody@example.com")
