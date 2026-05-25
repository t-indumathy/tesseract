"""UCP Capability Intersection Algorithm.

Implements the server-selects negotiation model from the spec:
https://ucp.dev/2026-04-08/specification/overview/#intersection-algorithm

Algorithm (verbatim from spec):
  1. Compute intersection: include capability if same name exists in both profiles.
  2. Select version: highest mutually-supported version string.
     Exclude capability if no mutual version exists.
  3. Prune orphaned extensions: remove capabilities whose `extends` parent
     is not in the intersection.
  4. Repeat step 3 until stable (handles transitive extension chains).

The result is returned as a dict keyed by capability name → selected version.
"""
from __future__ import annotations


def intersect_capabilities(
    business: dict[str, list[dict]],
    platform: dict[str, list[dict]],
) -> dict[str, str]:
    """
    Returns { capability_name: selected_version } for all active capabilities.

    Args:
        business: capabilities dict from the business UCP profile
        platform: capabilities dict from the platform UCP profile
    """
    # Step 1 + 2: find mutual names and pick highest shared version
    active: dict[str, str] = {}
    for cap_name, biz_entries in business.items():
        if cap_name not in platform:
            continue
        platform_entries = platform[cap_name]
        biz_versions = {e["version"] for e in biz_entries}
        plat_versions = {e["version"] for e in platform_entries}
        mutual = biz_versions & plat_versions
        if not mutual:
            continue  # no shared version — exclude
        # Highest version = max by string sort (YYYY-MM-DD format sorts correctly)
        active[cap_name] = max(mutual)

    # Steps 3 + 4: prune orphaned extensions (repeat until stable)
    changed = True
    while changed:
        changed = False
        to_remove = []
        for cap_name in list(active):
            # Find the `extends` value from business profile
            extends = _get_extends(business, cap_name)
            if extends is None:
                continue  # root capability — never pruned
            parents = [extends] if isinstance(extends, str) else extends
            # Prune if NONE of the declared parents are in active set
            if not any(p in active for p in parents):
                to_remove.append(cap_name)
        for cap_name in to_remove:
            del active[cap_name]
            changed = True

    return active


def _get_extends(business: dict[str, list[dict]], cap_name: str) -> str | list[str] | None:
    entries = business.get(cap_name, [])
    if not entries:
        return None
    return entries[0].get("extends")  # all versions share the same extends lineage


def build_response_capabilities(
    active: dict[str, str],
    operation_type: str,  # "checkout" | "cart" | "order"
) -> dict[str, list[dict]]:
    """
    Filter active capabilities to only those relevant for this operation type.
    Spec: https://ucp.dev/2026-04-08/specification/overview/#response-capability-selection

    Root capability relevance:
      - checkout operations → dev.ucp.shopping.checkout
      - cart operations     → dev.ucp.shopping.cart
      - order operations    → dev.ucp.shopping.order
    Extensions are relevant if any extends value matches the relevant root.
    """
    ROOT_RELEVANCE = {
        "checkout": "dev.ucp.shopping.checkout",
        "cart": "dev.ucp.shopping.cart",
        "order": "dev.ucp.shopping.order",
    }
    relevant_root = ROOT_RELEVANCE.get(operation_type)
    if not relevant_root:
        return {}

    result: dict[str, list[dict]] = {}
    for cap_name, version in active.items():
        if cap_name == relevant_root:
            result[cap_name] = [{"version": version}]
        else:
            # Include extension if it extends the relevant root
            # (Stored in active dict; re-check business profile for extends)
            # For simplicity in PoC: check if cap_name contains operation_type
            # or ends with a known extension of the relevant root
            if _is_extension_of(cap_name, relevant_root):
                result[cap_name] = [{"version": version}]
    return result


def _is_extension_of(cap_name: str, parent: str) -> bool:
    """Heuristic for PoC: extension names contain the parent's service segment."""
    # e.g. dev.ucp.shopping.ap2_mandate extends dev.ucp.shopping.checkout
    # In full impl, inspect the profile's `extends` field
    EXTENSION_MAP: dict[str, str] = {
        "dev.ucp.shopping.ap2_mandate": "dev.ucp.shopping.checkout",
        "dev.ucp.shopping.fulfillment": "dev.ucp.shopping.checkout",
        "dev.ucp.shopping.discount": "dev.ucp.shopping.checkout",
    }
    return EXTENSION_MAP.get(cap_name) == parent
