#!/usr/bin/env python3
import json
import urllib.request

BASE = "https://www.autoid.ro/wp-json/autoid-ai/v1"
SKU = "MC92N0-GP0SXEYA5WR"


def get_json(path):
    req = urllib.request.Request(
        BASE + path,
        headers={
            "Accept": "application/json",
            "User-Agent": "AutoID-MCP-Condition-Probe/0.4.0",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    health = get_json("/health")
    require(health.get("status") == "ok", "canonical API health is not ok")
    require(health.get("plugin_version") == "0.4.9", f"expected plugin 0.4.9, got {health.get('plugin_version')!r}")
    require(health.get("schema_version") == "autoid-ai/0.4.9", f"unexpected schema {health.get('schema_version')!r}")

    payload = get_json(f"/offers/{SKU}")
    require((payload.get("product") or {}).get("sku") == SKU, "offer endpoint resolved a different SKU")
    offers = payload.get("offers")
    require(isinstance(offers, dict), "offers contract is missing")

    new = offers.get("new")
    refurb = offers.get("refurbished")
    used = offers.get("used")
    require(isinstance(new, dict), "offers.new is missing")
    require(isinstance(refurb, dict), "offers.refurbished is missing")
    require(isinstance(used, dict), "offers.used is missing")

    require(refurb.get("enabled") is True, "refurbished offer is not enabled")
    require(used.get("enabled") is True, "used offer is not enabled")
    require(isinstance(refurb.get("stock"), (int, float)) and refurb.get("stock") > 0, "refurbished stock must be > 0")
    require(isinstance(used.get("stock"), (int, float)) and used.get("stock") > 0, "used stock must be > 0")
    require(refurb.get("available") is True, "refurbished offer is not available")
    require(used.get("available") is True, "used offer is not available")

    refurb_price = ((refurb.get("price") or {}).get("eur_ex_vat"))
    used_price = ((used.get("price") or {}).get("eur_ex_vat"))
    require(isinstance(refurb_price, (int, float)) and refurb_price > 0, "refurbished EUR ex-VAT price is missing")
    require(isinstance(used_price, (int, float)) and used_price > 0, "used EUR ex-VAT price is missing")

    print("=== LIVE CONDITION OFFER PROBE ===")
    print(json.dumps({
        "plugin_version": health.get("plugin_version"),
        "schema_version": health.get("schema_version"),
        "sku": SKU,
        "new": {
            "enabled": new.get("enabled"),
            "available": new.get("available"),
            "price_eur_ex_vat": ((new.get("price") or {}).get("eur_ex_vat")),
            "stock": new.get("stock"),
        },
        "refurbished": {
            "enabled": refurb.get("enabled"),
            "available": refurb.get("available"),
            "price_eur_ex_vat": refurb_price,
            "stock": refurb.get("stock"),
            "grade": refurb.get("grade"),
            "warranty_months": refurb.get("warranty_months"),
            "refurbisher": refurb.get("refurbisher"),
        },
        "used": {
            "enabled": used.get("enabled"),
            "available": used.get("available"),
            "price_eur_ex_vat": used_price,
            "stock": used.get("stock"),
            "grade": used.get("grade"),
            "warranty_months": used.get("warranty_months"),
        },
    }, ensure_ascii=False, indent=2))
    print("LIVE CONDITION OFFER PROBE PASSED")


if __name__ == "__main__":
    main()
