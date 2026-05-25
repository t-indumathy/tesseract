"""AP2 Mandate verifier — validates VC structure and proof integrity."""
from __future__ import annotations
import os
import hmac
import hashlib
import json
import time
from typing import Any
from dotenv import load_dotenv

load_dotenv()

_SECRET = os.getenv("AP2_MANDATE_SECRET", "dev-secret-change-me").encode()


def _verify_sig(credential_subject: dict[str, Any], claimed_sig: str) -> bool:
    canonical = json.dumps(credential_subject, sort_keys=True, separators=(",", ":"}).encode()
    expected = hmac.new(_SECRET, canonical, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, claimed_sig)


def verify_mandate(
    mandate: dict[str, Any],
    expected_type: str,  # "IntentMandate" or "CartMandate"
) -> tuple[bool, str]:
    """
    Verify an AP2 mandate VC.

    Checks:
    1. Correct VC type present
    2. Proof block exists
    3. HMAC signature is valid
    4. Mandate has not expired

    Returns (is_valid: bool, message: str)
    """
    try:
        vc_types = mandate.get("type", [])
        if expected_type not in vc_types:
            return False, f"Expected type '{expected_type}' not found in {vc_types}"

        proof = mandate.get("proof")
        if not proof or "value" not in proof:
            return False, "Missing or malformed proof block"

        subject = mandate.get("credentialSubject", {})

        # Expiry check
        expires_at = subject.get("expires_at", 0)
        if time.time() > expires_at:
            return False, f"Mandate expired at {expires_at}"

        # Signature check
        if not _verify_sig(subject, proof["value"]):
            return False, "Proof signature mismatch — mandate may have been tampered with"

        return True, "Mandate verified"

    except Exception as exc:
        return False, f"Verification error: {exc}"
