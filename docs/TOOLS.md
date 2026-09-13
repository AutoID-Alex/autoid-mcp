# AutoID MCP tools

The AutoID MCP currently exposes the following read-only tools.

| Tool | Purpose |
| --- | --- |
| `search_products` | Search products, grouped models and exact SKUs. |
| `list_product_groups` | Enumerate canonical grouped models exhaustively for catalog synchronization. |
| `get_product_group` | Retrieve a grouped product/model. |
| `list_product_variants` | List exact SKU variants for a grouped model, including price, stock and technical attributes. |
| `get_product` | Retrieve canonical data for an exact product/SKU. |
| `get_product_offer` | Retrieve current price, stock and availability for an exact SKU. |
| `get_related_products` | Retrieve evidence-backed accessories, consumables, software or service relationships. |
| `get_related_products_summary` | Retrieve a summarized view of product relationships. |
| `search_support` | Search AutoID Support Center resources by model and technical intent. |
| `fetch_support` | Fetch a selected verified support resource before relying on it. |
| `autoid_support_health` | Check availability of the AutoID Support Center source. |
| `autoid_api_health` | Check availability of the canonical AutoID product API. |

## Catalog discovery

`list_product_groups` is the only supported exhaustive grouped-model discovery path. It pages through the canonical AutoID API endpoint `/product-groups` using `limit` and `offset`, with optional `brand` and `lifecycle` filters.

Do not approximate full-catalog discovery by issuing wildcard, alphabetic or repeated `search_products` queries. Search is relevance-oriented and is not a completeness contract.

The canonical `/product-groups` endpoint must return a stable paginated collection with enough information to identify each model/group and total pagination state. MCP proxies that canonical response without inventing or deduplicating models itself.

## Product configuration

Where structured attributes are available, variant selection should use those attributes rather than numeric substring matching.

Examples include:

- print resolution (`203 dpi`, `300 dpi`, `600 dpi`)
- print method
- interfaces
- wireless connectivity
- printer options such as Cutter, Peeler, Rewinder or RFID encoder
- maximum print width
- maximum media width
- print speed
- print languages

A request such as `ZT610 600 dpi with Ethernet` should resolve the `ZT610` model first and then filter exact variants by structured resolution and interface values.

## Product relationship contract

WooCommerce `product_tag` values are the canonical compatibility identifiers used by product relationship discovery.

- Model identity must be stored and exposed as the clean model name, for example `TC27`, `ZT410` or `MC9300`.
- Lifecycle labels must not be embedded in the compatibility identifier. Values such as `ZT410 (Discontinued)` are invalid for the public compatibility contract.
- A discontinued model remains discoverable under its clean identifier, for example `ZT410`.
- Lifecycle state (`active`, `discontinued`, successor information, and similar status) belongs in dedicated lifecycle/status data where that source exposes it; it must not be inferred from or encoded into `product_tags`.
- Product categories describe the related child's product type; they are not compatibility evidence.
- `aid_compatibilitate` is not the canonical reverse-compatibility source.
- `aid_continut_kit` describes package contents only.

Reverse lookup for a model therefore means: return child products whose canonical `product_tags` contain the exact clean model identifier.

## Support resources

Technical resource searches should remain model-specific. If no verified support resource exists for the requested model/topic, the client should report that absence instead of substituting a nearby product or generic resource.
