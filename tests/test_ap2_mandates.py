"""Tests for AP2 mandate issuance and verification."""
import time
import pytest
from src.ap2.mandates import issue_intent_mandate, issue_cart_mandate
from src.ap2.verifier import verify_mandate


def test_intent_mandate_issues_and_verifies():
    mandate = issue_intent_mandate(
        user_id="user-test",
        agent_id="agent-test",
        merchant_id="merchant-test",
    )
    assert "IntentMandate" in mandate["type"]
    assert "proof" in mandate
    ok, msg = verify_mandate(mandate, "IntentMandate")
    assert ok, msg


def test_cart_mandate_issues_and_verifies():
    mandate = issue_cart_mandate(
        cart_id="cart-abc",
        cart_total_usd=162.0,
        items=[{"product_id": "prod-001", "quantity": 1}],
        agent_id="agent-test",
        merchant_id="merchant-test",
    )
    assert "CartMandate" in mandate["type"]
    ok, msg = verify_mandate(mandate, "CartMandate")
    assert ok, msg


def test_tampered_mandate_fails_verification():
    mandate = issue_intent_mandate(
        user_id="user-test",
        agent_id="agent-test",
        merchant_id="merchant-test",
    )
    # Tamper: inflate spending limit after issuance
    mandate["credentialSubject"]["spending_limit_usd"] = 999999.0
    ok, msg = verify_mandate(mandate, "IntentMandate")
    assert not ok
    assert "mismatch" in msg


def test_wrong_type_fails_verification():
    mandate = issue_intent_mandate(
        user_id="user-test",
        agent_id="agent-test",
        merchant_id="merchant-test",
    )
    ok, msg = verify_mandate(mandate, "CartMandate")  # wrong expected type
    assert not ok


def test_expired_mandate_fails():
    mandate = issue_intent_mandate(
        user_id="user-test",
        agent_id="agent-test",
        merchant_id="merchant-test",
    )
    # Force expiry into the past
    mandate["credentialSubject"]["expires_at"] = int(time.time()) - 1
    # Re-sign with the tampered subject so signature passes but expiry fails
    from src.ap2.mandates import _sign
    mandate["proof"]["value"] = _sign(mandate["credentialSubject"])
    ok, msg = verify_mandate(mandate, "IntentMandate")
    assert not ok
    assert "expired" in msg
