#!/usr/bin/env python3
import json
import sys
import traceback
from urllib.parse import urlparse

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
]

ZT610_SUPPORT_CASES = [
    ("zt610_support_manual", "ZT610 manual", ("manual", "guide")),
    ("zt610_support_firmware", "ZT610 firmware", ("firmware",)),
    ("zt610_support_quick_start", "ZT610 quick start", ("quick start", "quickstart", "quick-start")),
    ("zt610_support_driver", "ZT610 driver", ("driver",)),
]

# A verified support hit can point either to the AutoID Support Center itself
# or to the manufacturer's official Zebra source.
TRUSTED_SUPPORT_HOST_SUFFIXES = ("autoid.ro", "zebra.com")
FETCH_KEY_HINTS = (
    "id",
    "resource_id",
    "resourceId",
    "url",
    "uri",
    "href",
    "link",
    "resource",
    "target",
)


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


def decode_jsonish(value):
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped or stripped[0] not in "[{":
        return value
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return value


def walk(value, path=()):
    value = decode_jsonish(value)
    if isinstance(value, dict):
        for key, child in value.items():
            yield from walk(child, path + (str(key),))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk(child, path + (str(index),))
    else:
        yield path, value


def normalized_text(value):
    parts = []
    for path, leaf in walk(value):
        parts.extend(path)
        if leaf is not None:
            parts.append(str(leaf))
    return "\n".join(parts).lower()


def trusted_support_hosts(value):
    hosts = set()
    for _, leaf in walk(value):
        if not isinstance(leaf, str):
            continue
        for token in leaf.replace('"', " ").replace("'", " ").split():
            token = token.strip("(),[]{}<>.,;")
            if not token.startswith(("http://", "https://")):
                continue
            try:
                host = (urlparse(token).hostname or "").lower()
            except ValueError:
                continue
            if any(host == suffix or host.endswith("." + suffix) for suffix in TRUSTED_SUPPORT_HOST_SUFFIXES):
                hosts.add(host)
    return sorted(hosts)


def validate_support_search(result, case_name, aliases):
    text = normalized_text(result)
    if "zt610" not in text:
        raise SmokeFailure(f"{case_name}: response does not contain ZT610 evidence")
    if not any(alias in text for alias in aliases):
        raise SmokeFailure(
            f"{case_name}: response does not contain expected resource type; aliases={aliases}"
        )

    hosts = trusted_support_hosts(result)
    if not hosts:
        raise SmokeFailure(
            f"{case_name}: response has no trusted AutoID/Zebra support URL"
        )
    print(f"ASSERT {case_name}: model=ZT610 type={aliases[0]} trusted_hosts={hosts}")


def tool_by_name(tools, name):
    for tool in tools:
        if isinstance(tool, dict) and tool.get("name") == name:
            return tool
    raise SmokeFailure(f"tools/list did not expose {name}")


def fetch_schema(tool):
    schema = tool.get("inputSchema") or {}
    properties = schema.get("properties") or {}
    required = schema.get("required") or []
    if not isinstance(properties, dict) or not properties:
        raise SmokeFailure("fetch_support inputSchema has no properties")
    if not isinstance(required, list):
        required = []
    print(
        "FETCH SCHEMA: required="
        + json.dumps(required, ensure_ascii=False)
        + " properties="
        + json.dumps(sorted(properties), ensure_ascii=False)
    )
    return properties, required


def scalar_candidates(search_result):
    candidates = []
    seen = set()
    for path, leaf in walk(search_result):
        if not path or leaf is None or isinstance(leaf, (dict, list, bool)):
            continue
        value = str(leaf).strip()
        if not value or len(value) > 2048:
            continue
        key = path[-1]
        marker = (key, value)
        if marker not in seen:
            seen.add(marker)
            candidates.append((key, value))
    return candidates


def choose_fetch_value(property_name, candidates):
    exact = [value for key, value in candidates if key == property_name]
    if exact:
        return exact[0]

    lower_name = property_name.lower()
    case_insensitive = [value for key, value in candidates if key.lower() == lower_name]
    if case_insensitive:
        return case_insensitive[0]

    # Schema names sometimes differ slightly from search-result field names.
    if lower_name in {hint.lower() for hint in FETCH_KEY_HINTS}:
        for hint in FETCH_KEY_HINTS:
            for key, value in candidates:
                if key.lower() == hint.lower():
                    return value

    return None


def build_fetch_arguments(search_result, fetch_tool):
    properties, required = fetch_schema(fetch_tool)
    candidates = scalar_candidates(search_result)
    args = {}

    for property_name in required:
        value = choose_fetch_value(property_name, candidates)
        if value is None:
            available_keys = sorted({key for key, _ in candidates})
            raise SmokeFailure(
                "fetch_support: cannot map required property "
                f"{property_name!r} from search result; available keys={available_keys}"
            )
        args[property_name] = value

    if not required:
        for property_name in properties:
            value = choose_fetch_value(property_name, candidates)
            if value is not None:
                args[property_name] = value
                break

    if not args:
        raise SmokeFailure("fetch_support: could not derive arguments from selected search result")

    print("FETCH ARGS: " + json.dumps(args, ensure_ascii=False, sort_keys=True))
    return args


def validate_fetch_result(result):
    text = normalized_text(result)
    if "zt610" not in text:
        raise SmokeFailure("fetch_support: fetched resource does not contain ZT610 evidence")
    hosts = trusted_support_hosts(result)
    if hosts:
        print(f"ASSERT fetch_support: model=ZT610 trusted_hosts={hosts}")
    else:
        print("ASSERT fetch_support: model=ZT610; fetched content contains no external URL")


def run_zt610_support_contract(client, tools, passed, blocking_failed):
    fetch_tool = tool_by_name(tools, "fetch_support")
    first_search_result = None

    for case_name, query, aliases in ZT610_SUPPORT_CASES:
        print(f"\n===== GOLDEN PROBE: {case_name} [BLOCKING] =====")
        print("TOOL: search_support")
        print("ARGS: " + json.dumps({"query": query}, ensure_ascii=False, sort_keys=True))
        try:
            result = call_tool(client, "search_support", {"query": query})
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
            validate_support_search(result, case_name, aliases)
            if first_search_result is None:
                first_search_result = result
            passed.append((case_name, "BLOCKING"))
        except Exception as exc:
            error = str(exc)
            blocking_failed.append((case_name, error))
            print(f"FAIL: {error}")
            traceback.print_exc()

    print("\n===== GOLDEN PROBE: zt610_support_fetch [BLOCKING] =====")
    try:
        if first_search_result is None:
            raise SmokeFailure("No validated ZT610 support search result is available for fetch")
        arguments = build_fetch_arguments(first_search_result, fetch_tool)
        result = call_tool(client, "fetch_support", arguments)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        validate_fetch_result(result)
        passed.append(("zt610_support_fetch", "BLOCKING"))
    except Exception as exc:
        error = str(exc)
        blocking_failed.append(("zt610_support_fetch", error))
        print(f"FAIL: {error}")
        traceback.print_exc()


def main():
    client = MCPClient(ENDPOINT, timeout=30)
    client.initialize()
    tools = client.list_tools()

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

    run_zt610_support_contract(client, tools, passed, blocking_failed)

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

    print("\nSUCCESS: all blocking ZT610 golden queries and support semantics passed")


if __name__ == "__main__":
    main()
