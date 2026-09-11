#!/usr/bin/env python3
import json
import sys
import traceback
from mcp_smoke import MCPClient, SmokeFailure

ENDPOINT = "https://mcp.autoid.ro/mcp"

CASES = [
    ("tc27_relationships", "get_related_products", {"target": "TC27", "limit": 50}),
    ("tc27_relationship_summary", "get_related_products_summary", {"target": "TC27"}),
    ("zt610_group", "get_product_group", {"model": "ZT610"}),
    ("zt610_variants", "list_product_variants", {"model": "ZT610", "limit": 100, "offset": 0}),
    ("mc9300_exact_sku", "get_product", {"sku": "MC930B-GSHDG4RW"}),
    ("mc9300_offer", "get_product_offer", {"sku": "MC930B-GSHDG4RW"}),
    ("cab_squix_printhead", "get_related_products", {"target": "CAB SQUIX 2", "limit": 50}),
    ("zt610_support_manual", "search_support", {"query": "ZT610 manual"}),
    ("zt610_support_firmware", "search_support", {"query": "ZT610 firmware"}),
    ("zt610_support_quick_start", "search_support", {"query": "ZT610 quick start"}),
    ("zt610_support_driver", "search_support", {"query": "ZT610 driver"}),
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
    failed = []

    for case_name, tool_name, arguments in CASES:
        print(f"\n===== GOLDEN PROBE: {case_name} =====")
        print(f"TOOL: {tool_name}")
        print("ARGS: " + json.dumps(arguments, ensure_ascii=False, sort_keys=True))
        try:
            result = call_tool(client, tool_name, arguments)
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
            passed.append(case_name)
        except Exception as exc:
            failed.append((case_name, str(exc)))
            print(f"ERROR: {exc}")
            traceback.print_exc()

    print("\n===== GOLDEN PROBE SUMMARY =====")
    print(f"PASSED: {len(passed)}")
    for case_name in passed:
        print(f"  PASS {case_name}")

    print(f"FAILED: {len(failed)}")
    for case_name, error in failed:
        print(f"  FAIL {case_name}: {error}")

    if failed:
        sys.exit(1)

    print("\nSUCCESS: golden-query probe completed")


if __name__ == "__main__":
    main()
