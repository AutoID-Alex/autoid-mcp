#!/usr/bin/env python3
import json
import sys
import traceback
from mcp_smoke import MCPClient, SmokeFailure

ENDPOINT = "https://mcp.autoid.ro/mcp"

# ZT610 is the current blocking golden model because its product and
# manufacturer support data are complete. Other models remain exploratory
# until their catalog/support data are fully populated.
CASES = [
    ("tc27_relationships", "get_related_products", {"target": "TC27", "limit": 50}, False),
    ("tc27_relationship_summary", "get_related_products_summary", {"target": "TC27"}, False),
    ("zt610_group", "get_product_group", {"model": "ZT610"}, True),
    ("zt610_variants", "list_product_variants", {"model": "ZT610", "limit": 100, "offset": 0}, True),
    ("mc9300_exact_sku", "get_product", {"sku": "MC930B-GSHDG4RW"}, False),
    ("mc9300_offer", "get_product_offer", {"sku": "MC930B-GSHDG4RW"}, False),
    ("cab_squix_printhead", "get_related_products", {"target": "CAB SQUIX 2", "limit": 50}, False),
    ("zt610_support_manual", "search_support", {"query": "ZT610 manual"}, True),
    ("zt610_support_firmware", "search_support", {"query": "ZT610 firmware"}, True),
    ("zt610_support_quick_start", "search_support", {"query": "ZT610 quick start"}, True),
    ("zt610_support_driver", "search_support", {"query": "ZT610 driver"}, True),
]


def call_tool(client, tool_name, arguments):
    result = client.post(
        "tools/call",
        {
            "name": tool_name,
            "arguments": arguments,
        },
    )
    if not isinstance(result, dict):
        raise SmokeFailure(f"{tool_name} returned non-object result")
    if result.get("isError"):
        raise SmokeFailure(f"{tool_name} returned isError=true: {result}")
    return result


def main():
    client = MCPClient(ENDPOINT, timeout=30)
    client.initialize()

    passed = []
    blocking_failed = []
    observations = []

    for case_name, tool_name, arguments, blocking in CASES:
        mode = "BLOCKING" if blocking else "EXPLORATORY"
        print(f"\n===== GOLDEN PROBE: {case_name} [{mode}] =====")
        print(f"TOOL: {tool_name}")
        print("ARGS: " + json.dumps(arguments, ensure_ascii=False, sort_keys=True))
        try:
            result = call_tool(client, tool_name, arguments)
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
            passed.append((case_name, mode))
        except Exception as exc:
            error = str(exc)
            if blocking:
                blocking_failed.append((case_name, error))
                print(f"FAIL: {error}")
            else:
                observations.append((case_name, error))
                print(f"OBSERVE: {error}")
            traceback.print_exc()

    print("\n===== GOLDEN PROBE SUMMARY =====")
    print(f"PASSED: {len(passed)}")
    for case_name, mode in passed:
        print(f"  PASS [{mode}] {case_name}")

    print(f"EXPLORATORY OBSERVATIONS: {len(observations)}")
    for case_name, error in observations:
        print(f"  OBSERVE {case_name}: {error}")

    print(f"BLOCKING FAILURES: {len(blocking_failed)}")
    for case_name, error in blocking_failed:
        print(f"  FAIL {case_name}: {error}")

    if blocking_failed:
        sys.exit(1)

    print("\nSUCCESS: all blocking ZT610 golden queries passed")


if __name__ == "__main__":
    main()
