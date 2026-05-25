"""Tests for src/ap2/mandates.py — IntentMandate and CartMandate issuance."""
from __future__ import annotations
import time
import pytest

from src.ap2.mandates import issue_intent_mandate, issue_cart_mandate


class TestIntentMandate:
    def test_structure(self):
        m = issue_intent_mandate(
            user_id="user-1",
            agent_id="agent-1",
            merchant_id="merchant-1",
        )
        assert m["type"] == ["VerifiableCredential", "IntentMandate"]
        assert "proof" in m
        assert m["proof"]["type"] == "HmacSha256Proof2024"
        assert len(m["proof"]["value"]) == 64  # HMAC-SHA256 hex digest

    def test_credential_subject_fields(self):
        m = issue_intent_mandate("u", "a", "m", action="purchase", spending_limit_usd=200.0)
        cs = m["credentialSubject"]
        assert cs["action"] == "purchase"
        assert cs["spending_limit_usd"] == 200.0
        assert cs["expires_at"] > cs["issued_at"]

    def test_expiry_is_10_minutes(self):
        before = int(time.time())
        m = issue_intent_mandate("u", "a", "m")
        cs = m["credentialSubject"]
        assert cs["expires_at"] - cs["issued_at"] == 600

    def test_unique_ids(self):
        m1 = issue_intent_mandate("u", "a", "m")
        m2 = issue_intent_mandate("u", "a", "m")
        assert m1["id"] != m2["id"]


class TestCartMandate:
    def test_structure(self):
        m = issue_cart_mandate(
            cart_id="cart-1",
            cart_total_usd=149.99,
            items=[{"product_id": "prod-001", "quantity": 1}],
            agent_id="agent-1",
            merchant_id="merchant-1",
        )
        assert m["type"] == ["VerifiableCredential", "CartMandate"]
        assert "proof" in m
        assert m["credentialSubject"]["cart_total_usd"] == 149.99

    def test_unique_ids(self):
        m1 = issue_cart_mandate("c", 10.0, [], "a", "m")
        m2 = issue_cart_mandate("c", 10.0, [], "a", "m")
        assert m1["id"] != m2["id"]
