#!/usr/bin/env python3
import argparse
import json
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit, urlunsplit

EXPECTED_TOOLS = {
    "search_products",
    "get_product_group",
    "list_product_variants",
    "get_product",
    "get_product_offer",
    "get_related_products",
    "get_related_products_summary",
    "search_support",
    "fetch_support",
    "autoid_support_health",
    "autoid_api_health",
}


class SmokeFailure(RuntimeError):
    pass


def root_url(endpoint: str) -> str:
    parts = urlsplit(endpoint)
    return urlunsplit((parts.scheme, parts.netloc, "", "", "")).rstrip("/")


def http_get(url: str, timeout: int) -> tuple[int, str, dict]:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json, text/plain;q=0.9, */*;q=0.8",
            "User-Agent": "autoid-mcp-contract-test/1.0",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", "replace"), dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise SmokeFailure(f"GET {url} failed with HTTP {exc.code}: {body[:500]}") from exc
    except urllib.error.URLError as exc:
        raise SmokeFailure(f"GET {url} failed: {exc}") from exc


def parse_mcp_body(body: str, request_id=None):
    body = body.strip()
    if not body:
        return None

    try:
        return json.loads(body)
    except json.JSONDecodeError:
        pass

    events = []
    data_lines = []
    for raw_line in body.splitlines():
        line = raw_line.rstrip("\r")
        if not line:
            if data_lines:
                data = "\n".join(data_lines)
                data_lines = []
                try:
                    events.append(json.loads(data))
                except json.JSONDecodeError:
                    continue
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())

    if data_lines:
        try:
            events.append(json.loads("\n".join(data_lines)))
        except json.JSONDecodeError:
            pass

    if request_id is not None:
        for event in events:
            if isinstance(event, dict) and event.get("id") == request_id:
                return event

    if events:
        return events[0]

    raise SmokeFailure(f"Response was neither JSON nor parseable SSE: {body[:500]}")


class MCPClient:
    def __init__(self, endpoint: str, timeout: int):
        self.endpoint = endpoint
        self.timeout = timeout
        self.session_id = None
        self.protocol_version = None
        self.next_id = 1

    def post(self, method: str, params=None, notification: bool = False):
        request_id = None if notification else self.next_id
        if not notification:
            self.next_id += 1

        payload = {"jsonrpc": "2.0", "method": method}
        if request_id is not None:
            payload["id"] = request_id
        if params is not None:
            payload["params"] = params

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": "autoid-mcp-contract-test/1.0",
            "Mcp-Method": method,
        }
        if method == "tools/call" and isinstance(params, dict) and params.get("name"):
            headers["Mcp-Name"] = str(params["name"])
        if self.protocol_version:
            headers["MCP-Protocol-Version"] = self.protocol_version
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id

        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                body = response.read().decode("utf-8", "replace")
                session = response.headers.get("Mcp-Session-Id") or response.headers.get("MCP-Session-Id")
                if session:
                    self.session_id = session
                if notification:
                    return None
                message = parse_mcp_body(body, request_id=request_id)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            raise SmokeFailure(
                f"MCP {method} failed with HTTP {exc.code}: {body[:1000]}"
            ) from exc
        except urllib.error.URLError as exc:
            raise SmokeFailure(f"MCP {method} failed: {exc}") from exc

        if not isinstance(message, dict):
            raise SmokeFailure(f"MCP {method} returned an invalid message: {message!r}")
        if "error" in message:
            raise SmokeFailure(f"MCP {method} returned JSON-RPC error: {message['error']}")
        if "result" not in message:
            raise SmokeFailure(f"MCP {method} response has no result: {message}")
        return message["result"]

    def initialize(self):
        result = self.post(
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {
                    "name": "autoid-mcp-contract-test",
                    "version": "1.0.0",
                },
            },
        )
        if not isinstance(result, dict):
            raise SmokeFailure("Initialize result is not an object")

        negotiated = result.get("protocolVersion")
        if not isinstance(negotiated, str) or not negotiated:
            raise SmokeFailure("Initialize response did not include protocolVersion")
        self.protocol_version = negotiated

        capabilities = result.get("capabilities") or {}
        if "tools" not in capabilities:
            raise SmokeFailure("Server did not declare the tools capability")

        server_info = result.get("serverInfo") or {}
        print(
            f"OK initialize: protocol={self.protocol_version}, "
            f"server={server_info.get('name', 'unknown')} "
            f"{server_info.get('version', '')}".rstrip()
        )
        if self.session_id:
            print("OK session: server issued Mcp-Session-Id")

        self.post("notifications/initialized", notification=True)

    def list_tools(self):
        tools = []
        cursor = None
        seen_cursors = set()

        while True:
            params = {"cursor": cursor} if cursor else {}
            result = self.post("tools/list", params)
            page = result.get("tools") if isinstance(result, dict) else None
            if not isinstance(page, list):
                raise SmokeFailure("tools/list did not return a tools array")
            tools.extend(page)

            cursor = result.get("nextCursor")
            if not cursor:
                break
            if cursor in seen_cursors:
                raise SmokeFailure("tools/list returned a repeated pagination cursor")
            seen_cursors.add(cursor)

        return tools


def validate_health(endpoint: str, timeout: int):
    root = root_url(endpoint)
    for path in ("/health", "/ready"):
        status, body, _ = http_get(root + path, timeout)
        if status < 200 or status >= 300:
            raise SmokeFailure(f"{path} returned HTTP {status}")
        print(f"OK {path}: HTTP {status} {body.strip()[:160]}")


def validate_tools(tools: list, strict: bool):
    names = []
    for tool in tools:
        if not isinstance(tool, dict):
            raise SmokeFailure(f"Invalid tool entry: {tool!r}")
        name = tool.get("name")
        schema = tool.get("inputSchema")
        if not isinstance(name, str) or not name:
            raise SmokeFailure(f"Tool without a valid name: {tool!r}")
        if not isinstance(schema, dict) or schema.get("type") != "object":
            raise SmokeFailure(f"{name}: inputSchema must be an object schema")
        names.append(name)

        props = sorted((schema.get("properties") or {}).keys())
        required = schema.get("required") or []
        print(f"TOOL {name}: required={required} properties={props}")

    if len(names) != len(set(names)):
        raise SmokeFailure("tools/list returned duplicate tool names")

    actual = set(names)
    missing = EXPECTED_TOOLS - actual
    extra = actual - EXPECTED_TOOLS

    if missing:
        raise SmokeFailure(f"Missing expected tools: {sorted(missing)}")
    if strict and extra:
        raise SmokeFailure(f"Unexpected tools in strict mode: {sorted(extra)}")
    if strict and len(actual) != len(EXPECTED_TOOLS):
        raise SmokeFailure(
            f"Expected exactly {len(EXPECTED_TOOLS)} tools, got {len(actual)}"
        )

    print(f"OK tools/list: {len(actual)} tools")
    if extra:
        print(f"INFO additional tools: {sorted(extra)}")


def main():
    parser = argparse.ArgumentParser(description="AutoID remote MCP contract smoke test")
    parser.add_argument("--endpoint", default="https://mcp.autoid.ro/mcp")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument(
        "--strict-tools",
        action="store_true",
        help="Require exactly the documented AutoID tool set.",
    )
    args = parser.parse_args()

    validate_health(args.endpoint, args.timeout)

    client = MCPClient(args.endpoint, args.timeout)
    client.initialize()
    tools = client.list_tools()
    validate_tools(tools, args.strict_tools)

    print("SUCCESS: AutoID MCP live contract checks passed")


if __name__ == "__main__":
    try:
        main()
    except SmokeFailure as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
