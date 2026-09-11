#!/usr/bin/env python3
import json
import re

import golden_probe
from mcp_smoke import SmokeFailure


def has_wired_ethernet(value):
    """Accept explicit wired Ethernet evidence, never WLAN/wireless LAN alone."""
    norm = golden_probe.normalize_label(golden_probe.flattened_value(value))
    tokens = set(norm.split())

    if "ethernet" in tokens:
        return True
    if "rj45" in tokens or ("rj" in tokens and "45" in tokens):
        return True

    # LAN is accepted only as a standalone wired token and only when the same
    # value is not explicitly wireless/WLAN.
    if "lan" in tokens and "wlan" not in tokens and "wireless" not in tokens and "wi" not in tokens:
        return True

    return False


def envelope_exact_product_configuration(result, expected_sku):
    """Validate get_product's real envelope: product.sku and sibling attributes."""
    decoded = golden_probe.deep_decode(result)
    expected = expected_sku.strip().lower()
    diagnostics = []

    for obj in golden_probe.walk_objects(decoded):
        if not isinstance(obj, dict):
            continue

        product = obj.get("product")
        if not isinstance(product, dict):
            continue

        sku = golden_probe.direct_value_ci(product, golden_probe.SKU_KEYS)
        if sku is None or str(sku).strip().lower() != expected:
            continue

        resolution_matches, interface_matches = golden_probe.structured_configuration(obj)
        diagnostics.append(
            {
                "sku": str(sku),
                "resolution_matches": resolution_matches,
                "interface_matches": interface_matches,
                "attribute_keys": sorted((obj.get("attributes") or {}).keys())
                if isinstance(obj.get("attributes"), dict)
                else [],
            }
        )

        if resolution_matches and interface_matches:
            print(
                "ASSERT get_product envelope: sku=" + str(sku)
                + " resolution=" + json.dumps(resolution_matches, ensure_ascii=False, default=str)
                + " interfaces=" + json.dumps(interface_matches, ensure_ascii=False, default=str)
            )
            return

    # Defensive fallback for any future response that puts SKU and attributes
    # on the same object.
    for obj in golden_probe.walk_objects(decoded):
        if not isinstance(obj, dict):
            continue
        sku = golden_probe.direct_value_ci(obj, golden_probe.SKU_KEYS)
        if sku is None or str(sku).strip().lower() != expected:
            continue
        resolution_matches, interface_matches = golden_probe.structured_configuration(obj)
        if resolution_matches and interface_matches:
            print(
                "ASSERT get_product inline: sku=" + str(sku)
                + " resolution=" + json.dumps(resolution_matches, ensure_ascii=False, default=str)
                + " interfaces=" + json.dumps(interface_matches, ensure_ascii=False, default=str)
            )
            return

    raise SmokeFailure(
        f"get_product({expected_sku}) lacks structured 600 dpi + wired Ethernet evidence; "
        + "diagnostics=" + json.dumps(diagnostics, ensure_ascii=False, default=str)
    )


# Patch only the two semantics corrected by the focused live probe.
golden_probe.has_ethernet = has_wired_ethernet
golden_probe.validate_exact_product_configuration = envelope_exact_product_configuration


if __name__ == "__main__":
    golden_probe.main()
