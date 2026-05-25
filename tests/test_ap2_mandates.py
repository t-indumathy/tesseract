"""Tests for AP2 mandate issuance and verification."""
import time
from src.ap2.mandates import issue_intent_mandate, issue_cart_mandate, _sign
from src.ap2.verifier import verify_mandate


def test_intent_mandate_issues_and_verifies():
    m = issue_intent_mandate("u1", "a1", "m1")
    assert "IntentMandate" in m["type"]
    ok, msg = verify_mandate(m, "IntentMandate")
    assert ok, msg


def test_cart_mandate_issues_and_verifies():
    m = issue_cart_mandate("cart-1", 16200, [{"product_id": "prod-001"}], "a1", "m1")
    assert "CartMandate" in m["type"]
    ok, msg = verify_mandate(m, "CartMandate")
    assert ok, msg


def test_tampered_mandate_rejected():
    m = issue_intent_mandate("u1", "a1", "m1")
    m["credentialSubject"]["spending_limit_usd"] = 999999
    ok, msg = verify_mandate(m, "IntentMandate")
    assert not ok and "mismatch" in msg


def test_expired_mandate_rejected():
    m = issue_intent_mandate("u1", "a1", "m1")
    m["credentialSubject"]["expires_at"] = int(time.time()) - 1
    m["proof"]["value"] = _sign(m["credentialSubject"])  # re-sign so only expiry fails
    ok, msg = verify_mandate(m, "IntentMandate")
    assert not ok and "expired" in msg


def test_wrong_type_rejected():
    m = issue_intent_mandate("u1", "a1", "m1")
    ok, _ = verify_mandate(m, "CartMandate")
    assert not ok
