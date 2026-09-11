#!/usr/bin/env python3
import json

from mcp_smoke import MCPClient

ENDPOINT = "https://mcp.autoid.ro/mcp"
TARGET = "TC27"


def deep_decode(value):
    if isinstance(value, str):
        stripped = value.strip()
        if stripped and stripped[0] in "[{":
            try:
                return deep_decode(json.loads(stripped))
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


def walk_objects(value):
    value = deep_decode(value)
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_objects(child)


def value_ci(obj, names):
    if not isinstance(obj, dict):
        return None
    lookup = {str(k).lower(): v for k, v in obj.items()}
    for name in names:
        if name.lower() in lookup:
            return lookup[name.lower()]
    return None


def extract_skus(value):
    skus = []
    seen = set()
    for obj in walk_objects(value):
        sku = value_ci(obj, ("sku", "product_sku", "target_sku"))
        if sku is None:
            continue
        sku = str(sku).strip()
        if sku and sku not in seen and sku.upper() != TARGET:
            seen.add(sku)
            skus.append(sku)
    return skus


def print_product_evidence(client, sku):
    result = client.post("tools/call", {"name": "get_product", "arguments": {"sku": sku}})
    data = payload(result)
    print(f"\n--- CHILD PRODUCT {sku} ---")
    if isinstance(result, dict):
        print("isError:", bool(result.get("isError")))
    if not isinstance(data, dict):
        print(json.dumps(data, ensure_ascii=False, default=str)[:6000])
        return

    product = data.get("product") if isinstance(data.get("product"), dict) else {}
    print("name:", product.get("name"))
    print("canonical_url:", product.get("canonical_url"))

    for key in ("product_tags", "tags", "tag", "categories", "category", "product_categories", "relationship", "relations"):
        if key in data:
            print(f"{key}:", json.dumps(data[key], ensure_ascii=False, default=str)[:5000])
        if key in product:
            print(f"product.{key}:", json.dumps(product[key], ensure_ascii=False, default=str)[:5000])

    # Show all tag/category/compatibility-like paths for discovery.
    for obj in walk_objects(data):
        if not isinstance(obj, dict):
            continue
        interesting = {}
        for key, child in obj.items():
            low = str(key).lower()
            if any(token in low for token in ("tag", "categor", "compat", "relation", "role", "evidence", "source")):
                interesting[key] = child
        if interesting:
            print("evidence_object:", json.dumps(interesting, ensure_ascii=False, default=str)[:5000])


def main():
    client = MCPClient(ENDPOINT, timeout=30)
    client.initialize()

    rel_result = client.post(
        "tools/call",
        {"name": "get_related_products", "arguments": {"target": TARGET, "limit": 100}},
    )
    rel_payload = payload(rel_result)

    print("=== TC27 RELATIONSHIP DISCOVERY ===")
    print("Rule: compatibility is declared by product_tags on the CHILD product.")
    print("Target/reference model:", TARGET)
    if isinstance(rel_result, dict):
        print("get_related_products.isError:", bool(rel_result.get("isError")))
    print(json.dumps(rel_payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)[:30000])

    skus = extract_skus(rel_payload)
    print("\nRELATED SKUS FOUND:", json.dumps(skus, ensure_ascii=False))

    for sku in skus[:20]:
        print_product_evidence(client, sku)

    summary = client.post(
        "tools/call",
        {"name": "get_related_products_summary", "arguments": {"target": TARGET}},
    )
    print("\n=== TC27 RELATIONSHIP SUMMARY ===")
    print(json.dumps(payload(summary), ensure_ascii=False, indent=2, sort_keys=True, default=str)[:15000])


if __name__ == "__main__":
    main()
