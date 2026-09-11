#!/usr/bin/env python3
import json

from mcp_smoke import MCPClient
from golden_probe import deep_decode, walk

ENDPOINT = "https://mcp.autoid.ro/mcp"
SKU = "ZT61046-T2E0100Z"
NEEDLES = (
    "600 dpi",
    "Ethernet",
    "aid_rezolutie",
    "pa_aid_rezolutie",
    "aid_interfete",
    "pa_aid_interfete",
)


def call_tool(client, name, arguments):
    return client.post("tools/call", {"name": name, "arguments": arguments})


def decoded_payload(result):
    result = deep_decode(result)
    if isinstance(result, dict) and isinstance(result.get("structuredContent"), dict):
        return deep_decode(result["structuredContent"])
    return result


def print_paths(payload):
    print("\n=== VALUE PATHS ===")
    found = 0
    for path, leaf in walk(payload):
        if leaf is None:
            continue
        text = str(leaf)
        lower = text.lower()
        matches = [needle for needle in NEEDLES if needle.lower() in lower]
        if matches:
            found += 1
            print(json.dumps({"path": list(path), "value": leaf, "matches": matches}, ensure_ascii=False, default=str))
    if not found:
        print("NO TARGET VALUES FOUND")


def print_key_paths(value, path=()):
    value = deep_decode(value)
    if isinstance(value, dict):
        for key, child in value.items():
            key_lower = str(key).lower()
            if any(token in key_lower for token in ("attr", "spec", "technical", "taxonomy", "rezol", "interf")):
                preview = child
                if isinstance(preview, (dict, list)):
                    preview = json.dumps(preview, ensure_ascii=False, default=str)[:800]
                print(json.dumps({"path": list(path + (str(key),)), "preview": preview}, ensure_ascii=False, default=str))
            print_key_paths(child, path + (str(key),))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            print_key_paths(child, path + (str(index),))


def main():
    client = MCPClient(ENDPOINT, timeout=30)
    client.initialize()
    result = call_tool(client, "get_product", {"sku": SKU})
    payload = decoded_payload(result)

    print("=== ZT610 GET_PRODUCT PAYLOAD PROBE ===")
    print("SKU:", SKU)
    if isinstance(payload, dict):
        print("TOP_LEVEL_KEYS:", sorted(payload.keys()))
    else:
        print("PAYLOAD_TYPE:", type(payload).__name__)

    print("\n=== ATTRIBUTE-LIKE KEY PATHS ===")
    print_key_paths(payload)
    print_paths(payload)


if __name__ == "__main__":
    main()
