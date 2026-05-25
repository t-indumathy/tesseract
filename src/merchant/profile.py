"""Builds the UCP Business Profile served at /.well-known/ucp.

Spec: https://ucp.dev/2026-04-08/specification/overview/#business-profile

Key rules implemented here:
  - Capability names MUST use reverse-domain format (dev.ucp.*)
  - spec + schema URLs MUST be present for every capability
  - spec URL origin MUST match namespace authority (ucp.dev for dev.ucp.*)
  - AP2 mandate extension declared as dev.ucp.shopping.ap2_mandate
    extending dev.ucp.shopping.checkout
"""
from __future__ import annotations
import os
from src.merchant.models import (
    UCPProfile, UCPProfileBody,
    UCPServiceBinding, UCPCapabilityEntry,
)

BASE_URL = os.getenv("MERCHANT_BASE_URL", "http://localhost:8080")


def build_business_profile() -> UCPProfile:
    """
    Constructs the spec-compliant /.well-known/ucp profile.

    Capabilities declared:
      - dev.ucp.shopping.checkout   (root)
      - dev.ucp.shopping.cart       (root)
      - dev.ucp.shopping.order      (root)
      - dev.ucp.shopping.ap2_mandate (extension of checkout — AP2 trust layer)
    """
    return UCPProfile(
        ucp=UCPProfileBody(
            version="2026-04-08",
            services={
                # Service: dev.ucp.shopping over REST transport
                "dev.ucp.shopping": [
                    UCPServiceBinding(
                        version="2026-04-08",
                        spec="https://ucp.dev/2026-04-08/specification/overview",
                        transport="rest",
                        endpoint=f"{BASE_URL}/ucp/v1",
                        # Real OpenAPI schema from ucp.dev
                        schema="https://ucp.dev/2026-04-08/services/shopping/rest.openapi.json",
                    )
                ]
            },
            capabilities={
                # ── Root capabilities ──────────────────────────────────────
                "dev.ucp.shopping.checkout": [
                    UCPCapabilityEntry(
                        version="2026-04-08",
                        spec="https://ucp.dev/2026-04-08/specification/checkout",
                        schema="https://ucp.dev/2026-04-08/schemas/shopping/checkout.json",
                    )
                ],
                "dev.ucp.shopping.cart": [
                    UCPCapabilityEntry(
                        version="2026-04-08",
                        spec="https://ucp.dev/2026-04-08/specification/cart",
                        schema="https://ucp.dev/2026-04-08/schemas/shopping/cart.json",
                    )
                ],
                "dev.ucp.shopping.order": [
                    UCPCapabilityEntry(
                        version="2026-04-08",
                        spec="https://ucp.dev/2026-04-08/specification/order",
                        schema="https://ucp.dev/2026-04-08/schemas/shopping/order.json",
                    )
                ],
                # ── AP2 extension ──────────────────────────────────────────
                # dev.ucp.shopping.ap2_mandate extends checkout.
                # This declares that this merchant supports AP2 mandate
                # verification as part of the checkout capability.
                # Ref: https://ucp.dev/2026-04-08/specification/overview/#enhanced-security-for-autonomous-commerce
                "dev.ucp.shopping.ap2_mandate": [
                    UCPCapabilityEntry(
                        version="2026-04-08",
                        spec="https://ap2-protocol.org/specification",
                        schema="https://ap2-protocol.org/schemas/mandate.json",
                        # extends checkout — orphan-pruned if checkout not in intersection
                        extends="dev.ucp.shopping.checkout",
                    )
                ],
            },
        )
    )


def build_platform_profile() -> dict:
    """
    The platform (agent) side profile — served at /platform-profile in this PoC
    since both merchant and agent run on the same server locally.

    In production, this would be hosted at a stable HTTPS URL and advertised
    via the UCP-Agent header on every outbound request.
    """
    return {
        "ucp": {
            "version": "2026-04-08",
            "services": {
                "dev.ucp.shopping": [
                    {
                        "version": "2026-04-08",
                        "spec": "https://ucp.dev/2026-04-08/specification/overview",
                        "transport": "rest",
                        "schema": "https://ucp.dev/2026-04-08/services/shopping/rest.openapi.json",
                    }
                ]
            },
            "capabilities": {
                "dev.ucp.shopping.checkout": [
                    {
                        "version": "2026-04-08",
                        "spec": "https://ucp.dev/2026-04-08/specification/checkout",
                        "schema": "https://ucp.dev/2026-04-08/schemas/shopping/checkout.json",
                    }
                ],
                "dev.ucp.shopping.cart": [
                    {
                        "version": "2026-04-08",
                        "spec": "https://ucp.dev/2026-04-08/specification/cart",
                        "schema": "https://ucp.dev/2026-04-08/schemas/shopping/cart.json",
                    }
                ],
                "dev.ucp.shopping.ap2_mandate": [
                    {
                        "version": "2026-04-08",
                        "spec": "https://ap2-protocol.org/specification",
                        "schema": "https://ap2-protocol.org/schemas/mandate.json",
                        "extends": "dev.ucp.shopping.checkout",
                    }
                ],
            },
        }
    }
