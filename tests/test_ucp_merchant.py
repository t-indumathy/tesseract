"""Integration tests for the UCP Merchant Server."""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from src.merchant.server import app
from src.ap2.mandates import issue_intent_mandate, issue_cart_mandate


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def test_ucp_manifest(client):
    resp = await client.get("/.well-known/ucp-manifest")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ap2_supported"] is True
    cap_names = [c["name"] for c in data["capabilities"]]
    assert "checkout" in cap_names
    assert "ap2_mandate_verification" in cap_names


async def test_catalog_search(client):
    resp = await client.post("/ucp/catalog/search", json={"query": "headphones"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert any("Headphone" in p["name"] for p in data["products"])


async def test_create_cart(client):
    resp = await client.post(
        "/ucp/cart",
        json={"items": [{"product_id": "prod-001", "quantity": 1}], "buyer_agent_id": "test-agent"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "cart_id" in data
    assert data["total_usd"] > 0
    return data


async def test_full_checkout_with_valid_mandates(client):
    # Create cart
    cart_resp = await client.post(
        "/ucp/cart",
        json={"items": [{"product_id": "prod-001", "quantity": 1}], "buyer_agent_id": "test-agent"},
    )
    cart = cart_resp.json()

    intent = issue_intent_mandate("u1", "a1", "tesseract-demo-merchant")
    cart_mandate = issue_cart_mandate(
        cart_id=cart["cart_id"],
        cart_total_usd=cart["total_usd"],
        items=cart["items"],
        agent_id="a1",
        merchant_id="tesseract-demo-merchant",
    )

    resp = await client.post(
        "/ucp/checkout",
        json={
            "cart_id": cart["cart_id"],
            "intent_mandate": intent,
            "cart_mandate": cart_mandate,
            "payment_token": "tok_test",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "confirmed"


async def test_checkout_rejects_tampered_intent_mandate(client):
    cart_resp = await client.post(
        "/ucp/cart",
        json={"items": [{"product_id": "prod-001", "quantity": 1}], "buyer_agent_id": "test-agent"},
    )
    cart = cart_resp.json()

    intent = issue_intent_mandate("u1", "a1", "tesseract-demo-merchant")
    intent["credentialSubject"]["spending_limit_usd"] = 999999  # tamper!

    cart_mandate = issue_cart_mandate(
        cart_id=cart["cart_id"],
        cart_total_usd=cart["total_usd"],
        items=cart["items"],
        agent_id="a1",
        merchant_id="tesseract-demo-merchant",
    )

    resp = await client.post(
        "/ucp/checkout",
        json={
            "cart_id": cart["cart_id"],
            "intent_mandate": intent,
            "cart_mandate": cart_mandate,
            "payment_token": "tok_test",
        },
    )
    assert resp.status_code == 403
    assert "Intent Mandate invalid" in resp.json()["detail"]
