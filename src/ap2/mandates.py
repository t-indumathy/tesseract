"""AP2 Mandate issuance — Intent Mandate and Cart Mandate as Verifiable Credentials.

This PoC uses HMAC-SHA256 for signing (no DID/wallet required).
In production, replace with ECDSA P-256 over a W3C VC Data Model payload.

Ref: https://github.com/google-agentic-commerce/AP2
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

_SECRET = os.getenv("AP2_MANDATE_SECRET", "dev-secret-change-me").encode()


def _sign(payload: dict[str, Any]) -> str:
    """HMAC-SHA256 signature over canonical JSON (PoC substitute for VC proof)."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"}).encode()
    return hmac.new(_SECRET, canonical, hashlib.sha256).hexdigest()


def issue_intent_mandate(
    user_id: str,
    agent_id: str,
    merchant_id: str,
    action: str = "purchase",
    spending_limit_usd: float = 500.0,
) -> dict[str, Any]:
    """
    AP2 Intent Mandate — the user authorises the agent to act on their behalf.

    This is the non-repudiable proof that a human approved the agent's action.
    The mandate is a Verifiable Credential binding:
      user identity → agent identity → merchant → allowed action → spending limit.
    """
    issued_at = int(time.time())
    credential_subject = {
        "user_id": user_id,
        "agent_id": agent_id,
        "merchant_id": merchant_id,
        "action": action,
        "spending_limit_usd": spending_limit_usd,
        "issued_at": issued_at,
        "expires_at": issued_at + 600,  # 10-minute validity window
    }
    payload: dict[str, Any] = {
        "@context": ["https://www.w3.org/2018/credentials/v1"],
        "id": f"urn:ap2:intent:{uuid.uuid4()}",
        "type": ["VerifiableCredential", "IntentMandate"],
        "issuer": f"did:example:{user_id}",
        "issuanceDate": issued_at,
        "credentialSubject": credential_subject,
    }
    payload["proof"] = {
        "type": "HmacSha256Proof2024",
        "value": _sign(credential_subject),
    }
    return payload


def issue_cart_mandate(
    cart_id: str,
    cart_total_usd: float,
    items: list[dict[str, Any]],
    agent_id: str,
    merchant_id: str,
) -> dict[str, Any]:
    """
    AP2 Cart Mandate — cryptographically binds the cart snapshot to the agent.

    Prevents post-approval cart tampering. The merchant verifies this mandate
    before processing payment, ensuring the amount charged equals what the user saw.
    """
    issued_at = int(time.time())
    credential_subject = {
        "cart_id": cart_id,
        "agent_id": agent_id,
        "merchant_id": merchant_id,
        "cart_total_usd": cart_total_usd,
        "items": items,
        "issued_at": issued_at,
        "expires_at": issued_at + 600,
    }
    payload: dict[str, Any] = {
        "@context": ["https://www.w3.org/2018/credentials/v1"],
        "id": f"urn:ap2:cart:{uuid.uuid4()}",
        "type": ["VerifiableCredential", "CartMandate"],
        "issuer": f"did:example:{agent_id}",
        "issuanceDate": issued_at,
        "credentialSubject": credential_subject,
    }
    payload["proof"] = {
        "type": "HmacSha256Proof2024",
        "value": _sign(credential_subject),
    }
    return payload
