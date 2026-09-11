#!/usr/bin/env python3
import json
import re

from mcp_smoke import MCPClient

ENDPOINT = "https://mcp.autoid.ro/mcp"
TARGETS = ("TC27", "ZT410")
MAX_CHILDREN = 25

TAG_KEYS = ("product_tags", "tags", "tag_names", "tag_slugs", "product_tag")
SKU_KEYS = ("target_sku", "related_sku", "product_sku", "sku")
DISCONTINUED_PATTERN = re.compile(r"\(\s*discontinued\s*\)", re.IGNORECASE)


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


def extract_child_skus(value, target):
    skus = extract_values(value, SKU_KEYS)
    return [sku for sku in skus if sku.casefold() != target.casefold()]


def safe_tool(client, name, arguments):
    try:
        result = client.post("tools/call", {"name": name, "arguments": arguments})
    except Exception as exc:
        return None, f"transport_error:{exc}"
    if isinstance(result, dict) and result.get("isError"):
        return payload(result), "isError"
    return payload(result), "success"


def inspect_target(client, target):
    relations, relation_status = safe_tool(
        client,
        "get_related_products",
        {"target": target, "limit": 100},
    )

    print(f"\n=== MODEL TAG CONTRACT: {target} ===")
    print("model identity = exact clean product_tag value")
    print("lifecycle text must not be embedded in product_tags")
    print("get_related_products status:", relation_status)

    if relation_status != "success":
        print(json.dumps(relations, ensure_ascii=False, default=str)[:10000])
        raise RuntimeError(f"get_related_products failed for {target}: {relation_status}")

    skus = extract_child_skus(relations, target)[:MAX_CHILDREN]
    print("RELATED_SKUS:", json.dumps(skus, ensure_ascii=False))
    if not skus:
        raise AssertionError(f"No related SKUs returned for {target}")

    rows = []
    for sku in skus:
        product_data, product_status = safe_tool(client, "get_product", {"sku": sku})
        compatible_models = extract_values(product_data, TAG_KEYS) if product_status == "success" else []
        dirty_tags = [tag for tag in compatible_models if DISCONTINUED_PATTERN.search(tag)]
        exact_target = any(tag.casefold() == target.casefold() for tag in compatible_models)

        row = {
            "sku": sku,
            "product_status": product_status,
            "product_tags": compatible_models,
            "exact_target": exact_target,
            "dirty_lifecycle_tags": dirty_tags,
        }
        rows.append(row)
        print("CHILD:", json.dumps(row, ensure_ascii=False, default=str)[:7000])

    successful = [row for row in rows if row["product_status"] == "success"]
    missing_tags = [row["sku"] for row in successful if not row["product_tags"]]
    missing_exact_target = [
        row["sku"] for row in successful
        if row["product_tags"] and not row["exact_target"]
    ]
    dirty = {
        row["sku"]: row["dirty_lifecycle_tags"]
        for row in successful
        if row["dirty_lifecycle_tags"]
    }

    print("INSPECTED:", len(rows))
    print("PRODUCT_SUCCESS:", len(successful))
    print("MISSING_PRODUCT_TAGS:", json.dumps(missing_tags, ensure_ascii=False))
    print("MISSING_EXACT_TARGET:", json.dumps(missing_exact_target, ensure_ascii=False))
    print("DIRTY_LIFECYCLE_TAGS:", json.dumps(dirty, ensure_ascii=False))

    if not successful:
        raise AssertionError(f"No related SKU for {target} could be fetched with get_product")
    if missing_tags:
        raise AssertionError(
            f"Canonical get_product payload is missing product_tags for {target} relationships: "
            + ", ".join(missing_tags)
        )
    if missing_exact_target:
        raise AssertionError(
            f"Reverse compatibility lookup for {target} returned products without exact clean tag {target}: "
            + ", ".join(missing_exact_target)
        )
    if dirty:
        raise AssertionError(
            "Lifecycle labels are embedded in product_tags: "
            + json.dumps(dirty, ensure_ascii=False)
        )

    print(f"CONTRACT: PASS - {target} is an exact clean model tag and lifecycle text is separate")


def main():
    client = MCPClient(ENDPOINT, timeout=30)
    client.initialize()

    failures = []
    for target in TARGETS:
        try:
            inspect_target(client, target)
        except Exception as exc:
            failures.append(f"{target}: {exc}")
            print(f"CONTRACT: FAIL - {target}: {exc}")

    if failures:
        raise AssertionError("; ".join(failures))

    print("\nMODEL TAG LIFECYCLE CONTRACT: PASS")


if __name__ == "__main__":
    main()
