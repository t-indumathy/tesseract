# Copyright 2025 Google LLC  (Apache-2.0)
# Adapted from: google-agentic-commerce/AP2
#   code/samples/python/src/roles/credentials_provider_agent/tools.py
#   code/samples/python/src/roles/merchant_agent/tools.py
"""AP2 mandate verification helpers for the Tesseract PoC.

This module centralises the two verification patterns that appear across
both AP2 sample roles so the merchant server (server.py) and the
credentials layer share the same code path:

  1. Single-token (HNP / standard flow):
       ``<base64url-header>.<payload>.<sig>~<disclosure>...~<KB-JWT>``
     Verified with a pre-shared agent-provider public key.

  2. Chain (DPC immediate flow):
       ``DPC_sdjwt~~KB-SD-JWT~mandate_disc~agent_KB-JWT``
     Three-level delegation: DPC cnf → wallet key → KB-SD-JWT cnf →
     agent key → agent KB-JWT.  Verified with X5cOrKidPublicKeyProvider
     against a trusted root certificate.

Ref: https://github.com/google-agentic-commerce/AP2 (Apache-2.0)
"""
from __future__ import annotations
import logging
import os
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from jwcrypto.jwk import JWK
from pydantic import ValidationError

try:
    from ap2.sdk.generated.payment_mandate import PaymentMandate
    from ap2.sdk.generated.checkout_mandate import CheckoutMandate
    from ap2.sdk.mandate import MandateClient
    from ap2.sdk.sdjwt.chain import X5cOrKidPublicKeyProvider
    _AP2_AVAILABLE = True
except ImportError:
    # ap2-sdk not installed — fall back to stub mode for local dev/CI
    _AP2_AVAILABLE = False
    logging.warning(
        "[AP2] ap2-sdk not installed. Mandate verification running in STUB mode."
        " Install ap2-sdk to enable real verification."
    )

# Paths are resolved from env vars, mirroring the sample agent setup.
_AGENT_PROVIDER_PUB_KEY_PATH = os.environ.get("AGENT_PROVIDER_PUBLIC_KEY_PATH", "")
_CERTS_DIR = os.environ.get("AP2_CERTS_DIR", "certs")


def _load_pub_key():
    if _AGENT_PROVIDER_PUB_KEY_PATH and os.path.exists(_AGENT_PROVIDER_PUB_KEY_PATH):
        return load_pem_public_key(open(_AGENT_PROVIDER_PUB_KEY_PATH, "rb").read())
    raise ValueError(
        "Agent-provider public key not found. "
        "Set AGENT_PROVIDER_PUBLIC_KEY_PATH env var."
    )


def _load_trusted_roots() -> list:
    """Load trusted root certificates from the certs directory."""
    trusted_roots = []
    root_path = os.path.join(_CERTS_DIR, "issuer_cert_sdjwt.pem")
    if os.path.exists(root_path):
        with open(root_path, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read())
            trusted_roots.append(cert)
        logging.info("[AP2] Loaded trusted root cert: %s", root_path)
    else:
        logging.warning("[AP2] Trusted root cert not found at %s", root_path)
    return trusted_roots


# ─── PaymentMandate ────────────────────────────────────────────────────────────

def verify_payment_mandate(
    sdjwt: str,
    expected_aud: str | None = None,
    expected_nonce: str | None = None,
) -> Any:
    """
    Verify a PaymentMandate SD-JWT and return the parsed PaymentMandate model.

    Mirrors _verify_payment_mandate() from:
      credentials_provider_agent/tools.py

    Supports both HNP (single-token) and DPC immediate (chain, '~~') flows.

    Args:
        sdjwt: Serialised SD-JWT string.
        expected_aud: Expected audience claim (optional).
        expected_nonce: Expected nonce / checkout_jwt_hash (optional).

    Returns:
        PaymentMandate model on success, or raises ValueError / ValidationError.
    """
    if not _AP2_AVAILABLE:
        logging.warning("[AP2] STUB: skipping PaymentMandate verification.")
        return {"stub": True, "sdjwt_prefix": sdjwt[:40]}

    pub_key = _load_pub_key()
    trusted_roots = _load_trusted_roots()

    if "~~" in sdjwt:
        # DPC chain mode — three-level delegation
        tokens = sdjwt.split("~~")
        if len(tokens) < 2:
            raise ValueError(f"Expected ≥2 tokens in DPC chain, got {len(tokens)}")
        payloads = MandateClient().verify(
            token=sdjwt,
            key_or_provider=X5cOrKidPublicKeyProvider(
                lambda _kid: JWK.from_pyca(pub_key),
                trusted_roots=trusted_roots,
            ),
            expected_aud=expected_aud,
            expected_nonce=expected_nonce,
        )
        try:
            return PaymentMandate.model_validate(payloads[-1])
        except ValidationError as e:
            logging.warning("[AP2] PaymentMandate chain validate fallback: %s", e)
            return payloads[-1]

    # HNP single-token mode
    verified = MandateClient().verify(
        token=sdjwt,
        key_or_provider=JWK.from_pyca(pub_key),
        payload_type=PaymentMandate,
        expected_aud=expected_aud,
        expected_nonce=expected_nonce,
    )
    return verified.mandate_payload


# ─── CheckoutMandate ───────────────────────────────────────────────────────────

_MERCHANT_AUD = os.environ.get("MERCHANT_AUD", "https://merchant.com")
_MERCHANT_NONCE = os.environ.get("MERCHANT_NONCE", "merchant-nonce-xyz")


def verify_checkout_mandate(sdjwt: str) -> Any:
    """
    Verify a CheckoutMandate SD-JWT and return the parsed CheckoutMandate model.

    Mirrors _verify_checkout_mandate() from:
      merchant_agent/tools.py

    Args:
        sdjwt: Serialised SD-JWT string (single-token or DPC chain).

    Returns:
        CheckoutMandate model on success, or raises ValueError.
    """
    if not _AP2_AVAILABLE:
        logging.warning("[AP2] STUB: skipping CheckoutMandate verification.")
        return {"stub": True, "sdjwt_prefix": sdjwt[:40]}

    pub_key = _load_pub_key()
    trusted_roots = _load_trusted_roots()

    if "~~" in sdjwt:
        tokens = sdjwt.split("~~")
        if len(tokens) < 2:
            raise ValueError(f"Expected ≥2 tokens in DPC chain, got {len(tokens)}")
        payloads = MandateClient().verify(
            token=sdjwt,
            key_or_provider=X5cOrKidPublicKeyProvider(
                lambda _kid: JWK.from_pyca(pub_key),
                trusted_roots=trusted_roots,
            ),
            expected_aud=_MERCHANT_AUD,
            expected_nonce=_MERCHANT_NONCE,
        )
        try:
            # payloads[0] = DPC, payloads[1] = closed mandate
            return CheckoutMandate.model_validate(payloads[1])
        except ValidationError as e:
            logging.warning("[AP2] CheckoutMandate chain validate fallback: %s", e)
            return payloads[1]

    verified = MandateClient().verify(
        token=sdjwt,
        key_or_provider=JWK.from_pyca(pub_key),
        payload_type=CheckoutMandate,
    )
    logging.info(
        "[AP2] CheckoutMandate verified: checkout_hash=%s",
        verified.mandate_payload.mandate_payload.checkout_hash,
    )
    return verified.mandate_payload
