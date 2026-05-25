# Copyright 2025 Google LLC  (Apache-2.0)
# Adapted from: google-agentic-commerce/AP2
#   code/samples/python/src/roles/credentials_provider_agent/account_manager.py
"""In-memory stub credentials store for the Tesseract PoC.

Mirrors the account_manager.py pattern from the credentials_provider_agent
sample. In production this would be backed by a secure vault or HSM; for the
PoC it serves deterministic test fixtures so the flow runs end-to-end without
external dependencies.
"""
from __future__ import annotations
import uuid
from typing import Any

# ─── Stub account data ─────────────────────────────────────────────────────────
# Shape mirrors account_manager.get_account_payment_methods() output:
#   { alias, type, brand, network: [{name}], last4 }

_ACCOUNTS: dict[str, dict[str, Any]] = {
    "buyer@example.com": {
        "email": "buyer@example.com",
        "name": "Demo Buyer",
        "shipping_address": {
            "street": "123 Agent Lane",
            "city": "Mountain View",
            "state": "CA",
            "zip": "94043",
            "country": "US",
        },
        "payment_methods": [
            {
                "alias": "visa-4242",
                "type": "basic-card",
                "brand": "visa",
                "last4": "4242",
                "network": [{"name": "visa"}, {"name": "mastercard"}],
            },
            {
                "alias": "mastercard-5555",
                "type": "basic-card",
                "brand": "mastercard",
                "last4": "5555",
                "network": [{"name": "mastercard"}],
            },
        ],
    }
}

# transaction_id → payment token (set by handle_signed_payment_mandate)
_tokens: dict[str, str] = {}


# ─── API (mirrors account_manager.py) ─────────────────────────────────────────

def get_account_shipping_address(user_email: str) -> dict[str, Any]:
    account = _ACCOUNTS.get(user_email)
    if not account:
        raise ValueError(f"Account not found: {user_email}")
    return account["shipping_address"]


def get_account_payment_methods(user_email: str) -> list[dict[str, Any]]:
    account = _ACCOUNTS.get(user_email)
    if not account:
        raise ValueError(f"Account not found: {user_email}")
    return account["payment_methods"]


def create_token(user_email: str, payment_method_alias: str) -> str:
    """Mint a one-time payment token for the given alias."""
    account = _ACCOUNTS.get(user_email)
    if not account:
        raise ValueError(f"Account not found: {user_email}")
    method = next(
        (m for m in account["payment_methods"] if m["alias"] == payment_method_alias),
        None,
    )
    if not method:
        raise ValueError(f"Payment method {payment_method_alias!r} not found")
    token = f"tok_{uuid.uuid4().hex[:16]}"
    return token


def update_token_by_transaction_id(transaction_id: str) -> None:
    """Bind a transaction_id → stub token (mirrors account_manager upstream)."""
    _tokens[transaction_id] = f"bound_tok_{uuid.uuid4().hex[:12]}"


def get_credentials_by_transaction_id(transaction_id: str) -> dict[str, Any] | None:
    """Return raw credentials for a bound transaction."""
    token = _tokens.get(transaction_id)
    if not token:
        return None
    return {"token": token, "transaction_id": transaction_id, "type": "basic-card"}
