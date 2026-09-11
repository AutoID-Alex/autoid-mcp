#!/usr/bin/env python3
import json

from mcp_smoke import MCPClient

ENDPOINT = "https://mcp.autoid.ro/mcp"
TARGET = "ZT410"
EXPECTED_SUCCESSOR_ID = 169642


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


def find_key(value, key):
    value = deep_decode(value)
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for child in value.values():
            found = find_key(child, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_key(child, key)
            if found is not None:
                return found
    return None


def main():
    client = MCPClient(ENDPOINT, timeout=30)
    client.initialize()

    print("=== ZT410 LIFECYCLE / SUCCESSOR CONTRACT DISCOVERY ===")
    print("Compatibility relation engine is intentionally NOT used here.")
    print("Authoritative family successor source: AIDC Hub _autoid_support_successor_model_id")
    print("Expected configured successor ID:", EXPECTED_SUCCESSOR_ID)
    print("Commercial rule: successor exists as data at all times, but must not be promoted while the current ZT410 family has sellable stock.")

    health, health_status = safe_tool(client, "autoid_api_health", {})
    print("\n=== autoid_api_health ===")
    print("STATUS:", health_status)
    if health is not None:
        lifecycle_contract = find_key(health, "replacement_and_lifecycle")
        print("REPLACEMENT_LIFECYCLE_CONTRACT:", json.dumps(lifecycle_contract, ensure_ascii=False, default=str))

    group, group_status = safe_tool(
        client,
        "get_product_group",
        {"target": TARGET, "include_variants": False, "limit": 10},
    )
    print("\n=== get_product_group ZT410 ===")
    print("STATUS:", group_status)
    if group_status != "success":
        print(json.dumps(group, ensure_ascii=False, default=str)[:30000])
        print("READY_FOR_BLOCKING: false")
        return

    lifecycle = find_key(group, "lifecycle")
    if not isinstance(lifecycle, dict):
        print("LIFECYCLE_PRESENT: false")
        print("READY_FOR_BLOCKING: false")
        return

    model = lifecycle.get("model") if isinstance(lifecycle.get("model"), dict) else {}
    successor = lifecycle.get("successor") if isinstance(lifecycle.get("successor"), dict) else {}
    availability = lifecycle.get("current_family_availability") if isinstance(lifecycle.get("current_family_availability"), dict) else {}
    recommendation = lifecycle.get("successor_recommendation") if isinstance(lifecycle.get("successor_recommendation"), dict) else {}

    successor_id = successor.get("configured_id")
    family_available = availability.get("available_now")
    recommend_now = recommendation.get("recommend_now")
    reason = recommendation.get("reason")
    lifecycle_group = model.get("lifecycle_group")

    print("LIFECYCLE_PRESENT: true")
    print("MODEL_STATUS:", model.get("status"))
    print("LIFECYCLE_GROUP:", lifecycle_group)
    print("SUCCESSOR_ID:", successor_id)
    print("SUCCESSOR_NAME:", successor.get("name"))
    print("FAMILY_STOCK_AUTOID:", availability.get("stock_autoid"))
    print("FAMILY_STOCK_DISTRIBUTION:", availability.get("stock_distribution"))
    print("FAMILY_AVAILABLE:", family_available)
    print("AVAILABLE_MEMBER_COUNT:", availability.get("available_member_count"))
    print("RECOMMEND_NOW:", recommend_now)
    print("RECOMMEND_REASON:", reason)

    checks = []
    checks.append(("successor_id", successor_id == EXPECTED_SUCCESSOR_ID))
    checks.append(("lifecycle_discontinued", lifecycle_group == "discontinued"))

    if family_available is True:
        checks.append(("stock_gate", recommend_now is False and reason == "current_family_stock_available"))
    elif family_available is False:
        checks.append(("stock_gate", recommend_now is True and reason == "current_family_out_of_stock"))
    else:
        checks.append(("stock_gate", recommend_now is False and reason == "current_family_stock_unknown"))

    for name, passed in checks:
        print(f"CHECK {name}: {'PASS' if passed else 'FAIL'}")

    ready = all(passed for _, passed in checks)
    print("READY_FOR_BLOCKING:", str(ready).lower())


if __name__ == "__main__":
    main()
