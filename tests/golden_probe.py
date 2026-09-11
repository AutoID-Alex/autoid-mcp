#!/usr/bin/env python3
import json
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
    ("mc9300_support", "search_support", {"query": "MC9300 firmware manual"}),
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

    for case_name, tool_name, arguments in CASES:
        print(f"\n===== GOLDEN PROBE: {case_name} =====")
        print(f"TOOL: {tool_name}")
        print("ARGS: " + json.dumps(arguments, ensure_ascii=False, sort_keys=True))
        result = call_tool(client, tool_name, arguments)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))

    print("\nSUCCESS: golden-query probe completed")


if __name__ == "__main__":
    main()
