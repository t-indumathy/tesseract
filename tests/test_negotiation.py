"""Tests for the UCP capability intersection algorithm."""
import pytest
from src.merchant.negotiation import intersect_capabilities, build_response_capabilities

BIZ_CAPS = {
    "dev.ucp.shopping.checkout": [{"version": "2026-04-08", "spec": "https://ucp.dev/...", "schema": "https://ucp.dev/..."}],
    "dev.ucp.shopping.cart":     [{"version": "2026-04-08", "spec": "https://ucp.dev/...", "schema": "https://ucp.dev/..."}],
    "dev.ucp.shopping.ap2_mandate": [{"version": "2026-04-08", "spec": "https://ap2-protocol.org/...", "schema": "https://ap2-protocol.org/...", "extends": "dev.ucp.shopping.checkout"}],
}


def test_full_intersection():
    platform = {
        "dev.ucp.shopping.checkout":    [{"version": "2026-04-08", "spec": "x", "schema": "x"}],
        "dev.ucp.shopping.cart":        [{"version": "2026-04-08", "spec": "x", "schema": "x"}],
        "dev.ucp.shopping.ap2_mandate": [{"version": "2026-04-08", "spec": "x", "schema": "x", "extends": "dev.ucp.shopping.checkout"}],
    }
    active = intersect_capabilities(BIZ_CAPS, platform)
    assert "dev.ucp.shopping.checkout" in active
    assert "dev.ucp.shopping.cart" in active
    assert "dev.ucp.shopping.ap2_mandate" in active


def test_extension_pruned_when_parent_absent():
    """ap2_mandate must be pruned if checkout is not in platform profile."""
    platform = {
        "dev.ucp.shopping.cart": [{"version": "2026-04-08", "spec": "x", "schema": "x"}],
        # checkout absent → ap2_mandate (which extends checkout) must be pruned
        "dev.ucp.shopping.ap2_mandate": [{"version": "2026-04-08", "spec": "x", "schema": "x", "extends": "dev.ucp.shopping.checkout"}],
    }
    active = intersect_capabilities(BIZ_CAPS, platform)
    assert "dev.ucp.shopping.ap2_mandate" not in active  # pruned
    assert "dev.ucp.shopping.cart" in active


def test_version_mismatch_excludes_capability():
    platform = {
        "dev.ucp.shopping.checkout": [{"version": "2025-01-01", "spec": "x", "schema": "x"}],  # no mutual version
    }
    active = intersect_capabilities(BIZ_CAPS, platform)
    assert "dev.ucp.shopping.checkout" not in active


def test_response_caps_scoped_to_operation():
    active = {
        "dev.ucp.shopping.checkout": "2026-04-08",
        "dev.ucp.shopping.cart": "2026-04-08",
        "dev.ucp.shopping.ap2_mandate": "2026-04-08",
    }
    resp_caps = build_response_capabilities(active, "checkout")
    assert "dev.ucp.shopping.checkout" in resp_caps
    assert "dev.ucp.shopping.ap2_mandate" in resp_caps  # extends checkout
    assert "dev.ucp.shopping.cart" not in resp_caps     # not relevant to checkout op


def test_cart_op_excludes_checkout_caps():
    active = {
        "dev.ucp.shopping.checkout": "2026-04-08",
        "dev.ucp.shopping.cart": "2026-04-08",
        "dev.ucp.shopping.ap2_mandate": "2026-04-08",
    }
    resp_caps = build_response_capabilities(active, "cart")
    assert "dev.ucp.shopping.cart" in resp_caps
    assert "dev.ucp.shopping.checkout" not in resp_caps
    assert "dev.ucp.shopping.ap2_mandate" not in resp_caps
