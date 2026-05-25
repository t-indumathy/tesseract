"""Integration tests for the UCP Merchant Server."""
import pytest
from unittest.mock import patch
from httpx import AsyncClient, ASGITransport
from src.merchant.server import app
from src.ap2.mandates import issue_intent_mandate, issue_cart_mandate

PLATFORM_CAPS = {
    "dev.ucp.shopping.checkout":    [{"version": "2026-04-08", "spec": "x", "schema": "x"}],
    "dev.ucp.shopping.cart":        [{"version": "2026-04-08", "spec": "x", "schema": "x"}],
    "dev.ucp.shopping.ap2_mandate": [{"version": "2026-04-08", "spec": "x", "schema": "x", "extends": "dev.ucp.shopping.checkout"}],
}

# Mock _get_platform_caps so tests don't need a live profile URL
@pytest.fixture(autouse=True)
def mock_platform_caps():
    with patch("src.merchant.server._get_platform_caps", return_value=PLATFORM_CAPS):
        yield


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


UCP_AGENT = 'profile="http://localhost:8080/platform-profile"'


async def test_ucp_profile(client):
    resp = await client.get("/.well-known/ucp")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ucp"]["version"] == "2026-04-08"
    caps = data["ucp"]["capabilities"]
    assert "dev.ucp.shopping.checkout" in caps
    assert "dev.ucp.shopping.ap2_mandate" in caps
    # Verify spec URL origin matches namespace authority (ucp.dev for dev.ucp.*)
    checkout_spec = caps["dev.ucp.shopping.checkout"][0]["spec"]
    assert "ucp.dev" in checkout_spec


async def test_missing_ucp_agent_header_rejected(client):
    resp = await client.post("/ucp/v1/carts", json={"line_items": [], "buyer_agent_id": "x"})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "invalid_profile_url"


async def test_create_cart_amounts_in_cents(client):
    resp = await client.post(
        "/ucp/v1/carts",
        json={"line_items": [{"product_id": "prod-001", "quantity": 1}], "buyer_agent_id": "a1"},
        headers={"UCP-Agent": UCP_AGENT},
    )
    assert resp.status_code == 200
    data = resp.json()
    # UCP spec: amounts in minor units (cents)
    assert data["totals"]["total"] == int(149.99 * 100 * 1.08)  # price + 8% tax
    # ucp block echoed in response
    assert data["ucp"]["version"] == "2026-04-08"
    assert "dev.ucp.shopping.cart" in data["ucp"]["capabilities"]


async def test_full_checkout_spec_compliant(client):
    # Create cart
    cart_resp = await client.post(
        "/ucp/v1/carts",
        json={"line_items": [{"product_id": "prod-001", "quantity": 1}], "buyer_agent_id": "a1"},
        headers={"UCP-Agent": UCP_AGENT},
    )
    cart = cart_resp.json()

    intent = issue_intent_mandate("u1", "a1", "tesseract-demo-merchant")
    cart_m = issue_cart_mandate(
        cart_id=cart["id"],
        cart_total_cents=cart["totals"]["total"],
        line_items=cart["line_items"],
        agent_id="a1",
        merchant_id="tesseract-demo-merchant",
    )

    resp = await client.post(
        "/ucp/v1/checkout-sessions",
        json={"cart_id": cart["id"], "ap2": {"intent_mandate": intent, "cart_mandate": cart_m}, "payment_token": "tok"},
        headers={"UCP-Agent": UCP_AGENT},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    # ucp block with capabilities echoed back — mandatory per spec
    assert data["ucp"]["version"] == "2026-04-08"
    assert "dev.ucp.shopping.checkout" in data["ucp"]["capabilities"]
    assert "dev.ucp.shopping.ap2_mandate" in data["ucp"]["capabilities"]


async def test_checkout_without_mandates_rejected_when_ap2_active(client):
    cart_resp = await client.post(
        "/ucp/v1/carts",
        json={"line_items": [{"product_id": "prod-001", "quantity": 1}], "buyer_agent_id": "a1"},
        headers={"UCP-Agent": UCP_AGENT},
    )
    cart = cart_resp.json()
    resp = await client.post(
        "/ucp/v1/checkout-sessions",
        json={"cart_id": cart["id"], "payment_token": "tok"},  # no ap2 block
        headers={"UCP-Agent": UCP_AGENT},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "ap2_mandate_required"


async def test_tampered_intent_mandate_rejected(client):
    cart_resp = await client.post(
        "/ucp/v1/carts",
        json={"line_items": [{"product_id": "prod-001", "quantity": 1}], "buyer_agent_id": "a1"},
        headers={"UCP-Agent": UCP_AGENT},
    )
    cart = cart_resp.json()
    intent = issue_intent_mandate("u1", "a1", "tesseract-demo-merchant")
    intent["credentialSubject"]["spending_limit_usd"] = 999999  # tamper
    cart_m = issue_cart_mandate(
        cart_id=cart["id"], cart_total_cents=cart["totals"]["total"],
        line_items=cart["line_items"], agent_id="a1", merchant_id="tesseract-demo-merchant",
    )
    resp = await client.post(
        "/ucp/v1/checkout-sessions",
        json={"cart_id": cart["id"], "ap2": {"intent_mandate": intent, "cart_mandate": cart_m}},
        headers={"UCP-Agent": UCP_AGENT},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "intent_mandate_invalid"
