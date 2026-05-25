"""AP2 Mandate issuance.

Issues Intent Mandates and Cart Mandates as W3C Verifiable Credentials.

Official AP2 types package (install separately):
    uv pip install git+https://github.com/google-agentic-commerce/AP2.git@main

This module attempts to import from the official ap2 package first.
Falls back to a structurally-equivalent local implementation so the
PoC runs without the package installed.

Ref: https://github.com/google-agentic-commerce/AP2
Ref: https://ap2-protocol.org/specification
"""
from __future__ import annotations
import os
import hmac
import hashlib
import json
import time
import uuid
from typing import Any
from dotenv import load_dotenv

load_dotenv()

# Try official AP2 package first
try:
    from ap2.types import IntentMandate, CartMandate  # type: ignore
    _AP2_PACKAGE = True
except ImportError:
    _AP2_PACKAGE = False

_SECRET = os.getenv("AP2_MANDATE_SECRET", "dev-secret-change-me").encode()


def _sign(payload: dict[str, Any]) -> str:
    """HMAC-SHA256 PoC proof. Replace with ECDSA P-256 in production."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hmac.new(_SECRET, canonical, hashlib.sha256).hexdigest()


def issue_intent_mandate(
    user_id: str,
    agent_id: str,
    merchant_id: str,
    action: str = "purchase",
    spending_limit_usd: float = 500.0,
) -> dict[str, Any]:
    """
    AP2 Intent Mandate — non-repudiable proof that a human authorised the agent.

    Binds: user identity → agent identity → merchant → allowed action → spending cap.
    The mandate is a W3C Verifiable Credential.
    """
    if _AP2_PACKAGE:
        # Use official AP2 types when available
        mandate = IntentMandate(
            user_id=user_id,
            agent_id=agent_id,
            merchant_id=merchant_id,
            action=action,
            spending_limit_usd=spending_limit_usd,
        )
        return mandate.to_vc()

    # Fallback: structurally equivalent local implementation
    issued_at = int(time.time())
    subject = {
        "user_id": user_id,
        "agent_id": agent_id,
        "merchant_id": merchant_id,
        "action": action,
        "spending_limit_usd": spending_limit_usd,
        "issued_at": issued_at,
        "expires_at": issued_at + 600,
    }
    return {
        "@context": ["https://www.w3.org/2018/credentials/v1"],
        "id": f"urn:ap2:intent:{uuid.uuid4()}",
        "type": ["VerifiableCredential", "IntentMandate"],
        "issuer": f"did:example:{user_id}",
        "issuanceDate": issued_at,
        "credentialSubject": subject,
        "proof": {"type": "HmacSha256Proof2024", "value": _sign(subject)},
    }


def issue_cart_mandate(
    cart_id: str,
    cart_total_cents: int,
    line_items: list[dict[str, Any]],
    agent_id: str,
    merchant_id: str,
) -> dict[str, Any]:
    """
    AP2 Cart Mandate — cryptographically binds the cart snapshot to the agent.

    Prevents post-approval cart tampering. Merchant verifies before charging.
    Note: amounts in minor units (cents) per UCP spec.
    """
    if _AP2_PACKAGE:
        mandate = CartMandate(
            cart_id=cart_id,
            cart_total_cents=cart_total_cents,
            line_items=line_items,
            agent_id=agent_id,
            merchant_id=merchant_id,
        )
        return mandate.to_vc()

    issued_at = int(time.time())
    subject = {
        "cart_id": cart_id,
        "agent_id": agent_id,
        "merchant_id": merchant_id,
        "cart_total_cents": cart_total_cents,
        "line_items": line_items,
        "issued_at": issued_at,
        "expires_at": issued_at + 600,
    }
    return {
        "@context": ["https://www.w3.org/2018/credentials/v1"],
        "id": f"urn:ap2:cart:{uuid.uuid4()}",
        "type": ["VerifiableCredential", "CartMandate"],
        "issuer": f"did:example:{agent_id}",
        "issuanceDate": issued_at,
        "credentialSubject": subject,
        "proof": {"type": "HmacSha256Proof2024", "value": _sign(subject)},
    }
