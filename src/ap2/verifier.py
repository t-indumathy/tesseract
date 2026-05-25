"""AP2 Mandate verifier."""
from __future__ import annotations
import os
import hmac
import hashlib
import json
import time
from typing import Any
from dotenv import load_dotenv

load_dotenv()

try:
    from ap2.types import verify as ap2_verify  # type: ignore
    _AP2_PACKAGE = True
except ImportError:
    _AP2_PACKAGE = False

_SECRET = os.getenv("AP2_MANDATE_SECRET", "dev-secret-change-me").encode()


def _verify_sig(subject: dict[str, Any], claimed: str) -> bool:
    canonical = json.dumps(subject, sort_keys=True, separators=(",", ":")).encode()
    expected = hmac.new(_SECRET, canonical, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, claimed)


def verify_mandate(mandate: dict[str, Any], expected_type: str) -> tuple[bool, str]:
    """
    Verify an AP2 mandate VC.
    1. Correct type present
    2. Proof block exists
    3. Signature valid
    4. Not expired
    """
    if _AP2_PACKAGE:
        return ap2_verify(mandate, expected_type)

    try:
        if expected_type not in mandate.get("type", []):
            return False, f"Expected type '{expected_type}' not in {mandate.get('type')}"
        proof = mandate.get("proof")
        if not proof or "value" not in proof:
            return False, "Missing or malformed proof block"
        subject = mandate.get("credentialSubject", {})
        if time.time() > subject.get("expires_at", 0):
            return False, f"Mandate expired at {subject.get('expires_at')}"
        if not _verify_sig(subject, proof["value"]):
            return False, "Proof signature mismatch — mandate may have been tampered with"
        return True, "OK"
    except Exception as e:
        return False, f"Verification error: {e}"
