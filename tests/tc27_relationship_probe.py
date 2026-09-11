#!/usr/bin/env python3
import json
import re
from collections import Counter, defaultdict

from mcp_smoke import MCPClient

ENDPOINT = "https://mcp.autoid.ro/mcp"
TARGET = "TC27"
MAX_CHILDREN = 25

CHILD_SKU_KEYS = ("target_sku", "related_sku", "product_sku")
TAG_KEYS = ("product_tags", "tags", "tag_names", "tag_slugs", "product_tag")
CATEGORY_KEYS = (
    "categories",
    "category",
    "product_categories",
    "category_names",
    "category_slugs",
)


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


def walk(value, path=()):
    value = deep_decode(value)
    if isinstance(value, dict):
        yield path, value
        for key, child in value.items():
            yield from walk(child, path + (str(key),))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk(child, path + (str(index),))


def normalize_token(value):
    text = str(value).strip().lower()
    text = text.replace("ț", "t").replace("ţ", "t").replace("ș", "s").replace("ş", "s")
    text = text.replace("ă", "a").replace("â", "a").replace("î", "i")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


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


def relation_evidence_paths(value):
    interesting = []
    seen = set()
    for path, obj in walk(value):
        if not isinstance(obj, dict):
            continue
        for key, child in obj.items():
            low = str(key).lower()
            if not any(token in low for token in ("tag", "compat", "evidence", "source", "relation", "role", "category")):
                continue
            marker = path + (str(key),)
            if marker in seen:
                continue
            seen.add(marker)
            preview = child
            if isinstance(preview, (dict, list)):
                preview = json.dumps(preview, ensure_ascii=False, default=str)[:700]
            interesting.append({"path": list(marker), "preview": preview})
            if len(interesting) >= 120:
                return interesting
    return interesting


def extract_child_skus(value):
    preferred = []
    fallback = []
    seen_preferred = set()
    seen_fallback = set()

    for path, obj in walk(value):
        if not isinstance(obj, dict):
            continue
        lookup = {str(key).lower(): child for key, child in obj.items()}

        for key in CHILD_SKU_KEYS:
            if key not in lookup:
                continue
            for raw in scalar_strings(lookup[key]):
                sku = raw.strip()
                if sku and sku.upper() != TARGET and sku.lower() not in seen_preferred:
                    seen_preferred.add(sku.lower())
                    preferred.append(sku)

        if "sku" not in lookup:
            continue
        context = " ".join(part.lower() for part in path)
        relationish = any(
            token in context
            for token in ("related", "relation", "items", "results", "products", "accessor", "consum")
        ) or any(key in lookup for key in ("relation_type", "role", "canonical_url", "product_id", "category", "categories"))
        if not relationish:
            continue
        for raw in scalar_strings(lookup["sku"]):
            sku = raw.strip()
            if sku and sku.upper() != TARGET and sku.lower() not in seen_fallback:
                seen_fallback.add(sku.lower())
                fallback.append(sku)

    combined = []
    seen = set()
    for sku in preferred + fallback:
        if sku.lower() not in seen:
            seen.add(sku.lower())
            combined.append(sku)
    return combined


def extract_named_fields(value, allowed_keys):
    fields = []
    allowed = {key.lower() for key in allowed_keys}
    for path, obj in walk(value):
        if not isinstance(obj, dict):
            continue
        for key, child in obj.items():
            if str(key).lower() not in allowed:
                continue
            values = list(scalar_strings(child))
            fields.append({"path": list(path + (str(key),)), "values": values})
    return fields


def tag_evidence(product_payload):
    fields = extract_named_fields(product_payload, TAG_KEYS)
    if not fields:
        return "TAG_EVIDENCE_MISSING", [], []

    all_values = []
    for field in fields:
        all_values.extend(field["values"])
    matched = [value for value in all_values if normalize_token(value) == normalize_token(TARGET)]
    status = "TAG_CONFIRMED" if matched else "TAG_MISMATCH"
    return status, matched, fields


def category_evidence(product_payload):
    fields = extract_named_fields(product_payload, CATEGORY_KEYS)
    values = []
    seen = set()
    for field in fields:
        for value in field["values"]:
            key = value.lower()
            if key not in seen:
                seen.add(key)
                values.append(value)
    return values, fields


def classify_role(categories):
    text = " ".join(normalize_token(value) for value in categories)
    checks = (
        ("cable", ("cable", "cablu")),
        ("cradle", ("cradle", "dock", "docking")),
        ("power_supply", ("alimentator", "power supply", "psu", "power adapter", "adaptor alimentare")),
        ("case", ("husa", "case", "holster", "protective")),
        ("battery", ("battery", "baterie")),
        ("consumable", ("consumable", "consumabil", "ribbon", "ribon", "label", "eticheta")),
        ("software", ("software", "licenta", "license")),
        ("service", ("service", "garantie", "warranty")),
    )
    for role, aliases in checks:
        if any(alias in text for alias in aliases):
            return role
    return "unknown"


def compact_offer(offer_payload):
    if not isinstance(offer_payload, dict):
        return {"payload_type": type(offer_payload).__name__}
    compact = {}
    for key in ("product", "price", "pricing", "inventory", "availability", "freshness"):
        if key in offer_payload:
            compact[key] = offer_payload[key]
    return compact


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
    summary, summary_status = safe_tool(
        client,
        "get_related_products_summary",
        {"target": TARGET},
    )

    print("=== TC27 PRODUCT-TAG RELATIONSHIP DISCOVERY ===")
    print("Rule: CHILD product_tags declares compatibility with target/reference model TC27.")
    print("Role source: CHILD product category only.")
    print("aid_compatibilitate: ignored as compatibility authority.")
    print("aid_continut_kit: package contents only.")
    print("get_related_products status:", relation_status)
    print("get_related_products_summary status:", summary_status)

    print("\n=== RELATION RESPONSE EVIDENCE PATHS ===")
    for row in relation_evidence_paths(relations):
        print(json.dumps(row, ensure_ascii=False, default=str))

    if relation_status != "success":
        print("\nRELATIONSHIP_DISCOVERY_ERROR:", relation_status)
        print(json.dumps(relations, ensure_ascii=False, default=str)[:8000])
        print("\n=== TC27 RELATIONSHIP SUMMARY ===")
        print("RELATED_CHILDREN: 0")
        print("INSPECTED: 0")
        return

    skus = extract_child_skus(relations)
    print("\nRELATED SKUS FOUND:", json.dumps(skus[:MAX_CHILDREN], ensure_ascii=False))

    counters = Counter()
    role_counts = Counter()
    by_role = defaultdict(list)
    confirmed = []

    for sku in skus[:MAX_CHILDREN]:
        product_data, product_status = safe_tool(client, "get_product", {"sku": sku})
        if product_status != "success":
            counters["product_error"] += 1
            print(
                f"CHILD sku={sku} role=unknown categories=[] tag_status=TAG_EVIDENCE_MISSING "
                f"matched_tags=[] product_status={product_status} offer_status=not_run"
            )
            continue

        tag_status, matched_tags, tag_fields = tag_evidence(product_data)
        categories, category_fields = category_evidence(product_data)
        role = classify_role(categories)
        role_counts[role] += 1
        by_role[role].append(sku)
        counters[tag_status] += 1
        if tag_status == "TAG_CONFIRMED":
            confirmed.append(sku)

        offer_data, offer_status = safe_tool(client, "get_product_offer", {"sku": sku})
        if offer_status == "success":
            counters["offer_success"] += 1
        else:
            counters["offer_error"] += 1

        print(
            "CHILD "
            f"sku={sku} role={role} "
            f"categories={json.dumps(categories, ensure_ascii=False)} "
            f"tag_status={tag_status} matched_tags={json.dumps(matched_tags, ensure_ascii=False)} "
            f"product_status={product_status} offer_status={offer_status}"
        )
        print("  TAG_FIELDS:", json.dumps(tag_fields, ensure_ascii=False, default=str)[:2500])
        print("  CATEGORY_FIELDS:", json.dumps(category_fields, ensure_ascii=False, default=str)[:2500])
        print("  OFFER:", json.dumps(compact_offer(offer_data), ensure_ascii=False, default=str)[:5000])

    print("\n=== TC27 RELATIONSHIP SUMMARY ===")
    print("RELATED_CHILDREN:", len(skus))
    print("INSPECTED:", min(len(skus), MAX_CHILDREN))
    print("TAG_CONFIRMED:", counters["TAG_CONFIRMED"])
    print("TAG_EVIDENCE_MISSING:", counters["TAG_EVIDENCE_MISSING"])
    print("TAG_MISMATCH:", counters["TAG_MISMATCH"])
    print("ROLE_COUNTS:", json.dumps(dict(role_counts), ensure_ascii=False, sort_keys=True))
    print("OFFER_SUCCESS:", counters["offer_success"])
    print("OFFER_ERROR:", counters["offer_error"])
    print("CONFIRMED_SKUS:", json.dumps(confirmed, ensure_ascii=False))
    print("BY_ROLE:", json.dumps(dict(by_role), ensure_ascii=False, sort_keys=True))

    print("\n=== RAW RELATION SUMMARY ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True, default=str)[:10000])


if __name__ == "__main__":
    main()
