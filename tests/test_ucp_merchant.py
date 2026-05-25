"""Additional merchant server tests (supplements test_e2e_ucp_ap2.py).

Focuses on the mandate issuance → checkout round-trip using the
hmac-based raw-dict path that does NOT require ap2-sdk.
"""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient

from src.merchant.server import app
from src.ap2.mandates import issue_intent_mandate, issue_cart_mandate

client = TestClient(app)


@pytest.fixture()
def cart():
    """Create a fresh cart and return the full response body."""
    r = client.post("/ucp/cart", json={
        "items": [{"product_id": "prod-001", "quantity": 1}],
        "buyer_agent_id": "test-agent",
    })
    assert r.status_code == 200
    return r.json()


class TestMandateRoundTrip:
    def test_full_flow_intent_and_cart_mandate(self, cart):
        """Issue both mandates then checkout — simulates a shopping agent."""
        intent = issue_intent_mandate(
            user_id="buyer@example.com",
            agent_id="test-agent",
            merchant_id="tesseract-demo-merchant",
        )
        cart_m = issue_cart_mandate(
            cart_id=cart["cart_id"],
            cart_total_usd=cart["total_usd"],
            items=cart["items"],
            agent_id="test-agent",
            merchant_id="tesseract-demo-merchant",
        )
        r = client.post("/ucp/checkout", json={
            "cart_id": cart["cart_id"],
            "intent_mandate": intent,
            "cart_mandate": cart_m,
        })
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "confirmed"
        assert "order_id" in body
        assert body["total_usd"] == cart["total_usd"]

    def test_intent_mandate_proof_present(self, cart):
        intent = issue_intent_mandate("u", "a", "m")
        assert "proof" in intent
        assert intent["proof"]["type"] == "HmacSha256Proof2024"

    def test_cart_mandate_total_matches_cart(self, cart):
        cart_m = issue_cart_mandate(
            cart_id=cart["cart_id"],
            cart_total_usd=cart["total_usd"],
            items=cart["items"],
            agent_id="a",
            merchant_id="m",
        )
        assert cart_m["credentialSubject"]["cart_total_usd"] == cart["total_usd"]
        assert cart_m["credentialSubject"]["cart_id"] == cart["cart_id"]
