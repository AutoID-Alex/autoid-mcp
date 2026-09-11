#!/usr/bin/env python3
import json

from mcp_smoke import MCPClient

ENDPOINT = "https://mcp.autoid.ro/mcp"
TARGET = "ZT410"
SUPPORT_URL = "https://www.autoid.ro/support/zebra/zt410-discontinued/"


def deep_decode(value):
    if isinstance(value, str):
        text = value.strip()
        if text and text[0] in "[{":
            try:
                return deep_decode(json.loads(text))
            except json.JSONDecodeError:
                return value
        return value
    if isinstance(value, dict):
        return {key: deep_decode(child) for key, child in value.items()}
    if isinstance(value, list):
        return [deep_decode(child) for child in value]
    return value


def payload(result):
    result = deep_decode(result)
    if isinstance(result, dict) and result.get("structuredContent") is not None:
        return deep_decode(result["structuredContent"])
    return result


def safe_tool(client, name, arguments):
    try:
        result = client.post("tools/call", {"name": name, "arguments": arguments})
    except Exception as exc:
        return None, f"transport_error:{exc}"
    if isinstance(result, dict) and result.get("isError"):
        return payload(result), "isError"
    return payload(result), "success"


def emit(name, status, data):
    print(f"\n=== {name} ===")
    print("STATUS:", status)
    print(json.dumps(data, ensure_ascii=False, default=str, indent=2)[:30000])


def main():
    client = MCPClient(ENDPOINT, timeout=30)
    client.initialize()

    print("=== ZT410 DISCONTINUED / SUCCESSOR DISCOVERY ===")
    print("Expected authoritative mapping configured in AutoID Support Center: ZT410 -> ZT411")
    print("This probe is discovery-only. It does not infer replacement from names or descriptions.")

    calls = [
        (
            "search_support",
            "search_support",
            {
                "brand": "Zebra",
                "model": TARGET,
                "include_discontinued": True,
                "page": 1,
                "per_page": 20,
            },
        ),
        (
            "fetch_support_model_page",
            "fetch_support",
            {"url": SUPPORT_URL},
        ),
        (
            "get_product_group",
            "get_product_group",
            {"target": TARGET, "include_variants": False, "limit": 10},
        ),
        (
            "search_products",
            "search_products",
            {"query": TARGET, "active_only": False, "limit": 10},
        ),
        (
            "get_related_products_summary",
            "get_related_products_summary",
            {"target": TARGET},
        ),
        (
            "get_related_products_replacement",
            "get_related_products",
            {"target": TARGET, "relation_type": "replacement", "limit": 20},
        ),
        (
            "get_related_products_successor",
            "get_related_products",
            {"target": TARGET, "relation_type": "successor", "limit": 20},
        ),
    ]

    for label, tool_name, arguments in calls:
        data, status = safe_tool(client, tool_name, arguments)
        emit(label, status, data)


if __name__ == "__main__":
    main()
