#!/usr/bin/env python3
import json

from mcp_smoke import MCPClient

ENDPOINT = "https://mcp.autoid.ro/mcp"
TARGET = "TC27"
MAX_CHILDREN = 25

TAG_KEYS = ("product_tags", "tags", "tag_names", "tag_slugs", "product_tag")
CATEGORY_KEYS = (
    "categories",
    "category",
    "product_categories",
    "category_names",
    "category_slugs",
)
SKU_KEYS = ("target_sku", "related_sku", "product_sku", "sku")


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


def walk(value):
    value = deep_decode(value)
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def scalar_strings(value):
    value = deep_decode(value)
    if isinstance(value, dict):
        for child in value.values():
            yield from scalar_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from scalar_strings(child)
    elif value is not None and not isinstance(value, bool):
        text = str(value).strip()
        if text:
            yield text


def unique(values):
    result = []
    seen = set()
    for value in values:
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result


def extract_values(value, keys):
    wanted = {key.casefold() for key in keys}
    found = []
    for obj in walk(value):
        if not isinstance(obj, dict):
            continue
        for key, child in obj.items():
            if str(key).casefold() in wanted:
                found.extend(scalar_strings(child))
    return unique(found)


def extract_child_skus(value):
    skus = extract_values(value, SKU_KEYS)
    return [sku for sku in skus if sku.casefold() != TARGET.casefold()]


def compact_offer(value):
    if not isinstance(value, dict):
        return value
    return {
        key: value[key]
        for key in ("product", "price", "pricing", "inventory", "availability", "freshness")
        if key in value
    }


def safe_tool(client, name, arguments):
    try:
        result = client.post("tools/call", {"name": name, "arguments": arguments})
    except Exception as exc:
        return None, f"transport_error:{exc}"
    if isinstance(result, dict) and result.get("isError"):
        return payload(result), "isError"
    return payload(result), "success"


def main():
    client = MCPClient(ENDPOINT, timeout=30)
    client.initialize()

    relations, relation_status = safe_tool(
        client,
        "get_related_products",
        {"target": TARGET, "limit": 100},
    )

    print("=== AUTOID COMPATIBILITY RULE ===")
    print("compatible_models = complete child product_tags list")
    print("reverse lookup(model) = products whose product_tags contain that model")
    print("categories describe the child product type only")
    print("aid_compatibilitate is ignored")
    print("aid_continut_kit is package contents only")
    print("target:", TARGET)
    print("get_related_products status:", relation_status)

    if relation_status != "success":
        print("RELATIONSHIP_DISCOVERY_ERROR:", relation_status)
        print(json.dumps(relations, ensure_ascii=False, default=str)[:10000])
        return

    skus = extract_child_skus(relations)[:MAX_CHILDREN]
    print("RELATED_SKUS:", json.dumps(skus, ensure_ascii=False))

    rows = []
    for sku in skus:
        product_data, product_status = safe_tool(client, "get_product", {"sku": sku})
        compatible_models = extract_values(product_data, TAG_KEYS) if product_status == "success" else []
        categories = extract_values(product_data, CATEGORY_KEYS) if product_status == "success" else []
        offer_data, offer_status = safe_tool(client, "get_product_offer", {"sku": sku})

        row = {
            "sku": sku,
            "categories": categories,
            "compatible_models": compatible_models,
            "contains_target": any(tag.casefold() == TARGET.casefold() for tag in compatible_models),
            "product_status": product_status,
            "offer_status": offer_status,
            "offer": compact_offer(offer_data) if offer_status == "success" else None,
        }
        rows.append(row)
        print("CHILD:", json.dumps(row, ensure_ascii=False, default=str)[:7000])

    print("\n=== SUMMARY ===")
    print("INSPECTED:", len(rows))
    print("WITH_PRODUCT_TAGS:", sum(bool(row["compatible_models"]) for row in rows))
    print("TAGGED_TC27:", sum(row["contains_target"] for row in rows))
    print("OFFER_SUCCESS:", sum(row["offer_status"] == "success" for row in rows))


if __name__ == "__main__":
    main()
