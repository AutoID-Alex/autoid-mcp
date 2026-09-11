# AutoID MCP Server v0.3.1

Read-only MCP server over the AutoID canonical WordPress/WooCommerce API.

This release includes the product, offer, grouped-variant and related-product behavior validated with the AutoID canonical API plugin v0.3.9.

## MCP tools

- `search_products`
- `get_product_group`
- `list_product_variants`
- `get_product`
- `get_product_offer`
- `get_related_products`
- `get_related_products_summary`
- `search_support`
- `fetch_support`
- `autoid_support_health`
- `autoid_api_health`

## Source of truth

The MCP server does not read WordPress SQL and does not calculate commercial or compatibility data itself. It reads the canonical API at:

`https://www.autoid.ro/wp-json/autoid-ai/v1`

Authoritative commercial fields:

- exact SKU MSRP EUR ex VAT: `pret_lista`
- exact SKU AutoID price EUR ex VAT: `pret_autoid_euro`
- grouped catalog MSRP from: `grp_pret_lista_mic`
- grouped catalog AutoID from: `grp_pret_autoid_mic`
- AutoID stock: `stock_autoid`
- distribution stock: `stock_distributie`

For a current exact-SKU price/stock answer, use `get_product_offer`. For Romanian customer-facing price output, use the canonical `ron_display` projection and prefer the inc-VAT value. RON is sourced from WooCommerce `_regular_price` / `_sale_price`; do not convert authoritative EUR prices into RON inside MCP.

## RON display pricing

Canonical API v0.3.9 adds a compact RON projection without changing commercial authority.

Exact SKU cards use `pricing.ron_display`; exact live offers use `price.ron_display`. Typical fields are `msrp_ex_vat`, `msrp_inc_vat`, `autoid_ex_vat`, and `autoid_inc_vat`. Grouped products use FROM fields such as `msrp_from_inc_vat` and `autoid_from_inc_vat`.

Rules:

- customer-facing Romanian answer: prefer RON `inc_vat`
- B2B/ex-VAT context: RON `ex_vat` may also be shown
- EUR `pret_lista` / `pret_autoid_euro` remain the commercial authority
- RON values are WooCommerce storefront display/validation data
- never calculate RON by applying an FX rate to the EUR authority inside MCP


## Related-product contract

`get_related_products` reads:

`/wp-json/autoid-ai/v1/relations/{sku-or-model}`

Supported relation types:

- `accessory` - stock-managed
- `consumable` - stock-managed
- `software` - not stock-managed
- `service_contract` - not stock-managed
- `all`

Compatibility is accepted only from the canonical API's `product_tag` evidence. WooCommerce `product_cat` determines whether the related entity is an accessory, consumable, software item or service contract.

For accessories and consumables, MCP defaults to `availability=available`:

`stock_autoid > 0 OR stock_distributie > 0`

The canonical API ranks AutoID stock before distribution-only stock. Out-of-stock items are intentionally extra catalog information and are not returned by default. Request `availability=out_of_stock` or `availability=all` only when needed.

For large consumable sets, filter using an exact category slug. Validated ZT610 examples include:

- `ribboane-imprimanta`
- `role-de-etichete`
- `intretinere-imprimante`

`get_related_products_summary` queries `availability=all` with a one-item page, then returns a compact projection of the canonical summary. Use it for total compatibility counts and out-of-stock counts without loading hundreds of catalog items into MCP context.

## Validated datasets

MC9300 full relation graph at validation time:

- 85 accessories
- 23 software entities = 22 exact SKUs + 1 grouped product
- 130 service contracts
- 0 consumables
- 238 related entities total

ZT610 full relation graph at validation time:

- 85 accessories
- 752 consumables
- 29 software entities = 28 exact SKUs + 1 grouped product
- 69 service contracts
- 935 related entities total

ZT610 consumables at validation time:

- 32 with AutoID stock
- 206 supplier-only
- 514 out of stock

These numbers are validation snapshots, not hard-coded production data. MCP always reads the live canonical API.

## Requirements

- Node.js 20+
- public HTTPS hostname, recommended `mcp.autoid.ro`
- outbound HTTPS access to `www.autoid.ro`

No WordPress DB access, WooCommerce API key or WordPress administrator credentials are required.

## Fresh install

```bash
unzip autoid-mcp-v0.3.1.zip
cd autoid-mcp-v0.3.1
npm install
cp .env.example .env
npm run build
npm run smoke:api
npm start
```

Environment variables:

```env
AUTOID_API_BASE=https://www.autoid.ro/wp-json/autoid-ai/v1
MCP_PUBLIC_HOST=mcp.autoid.ro
PORT=3000
AUTOID_API_TIMEOUT_MS=15000
```

The public MCP endpoint is:

`https://mcp.autoid.ro/mcp`

HTTP process health:

`https://mcp.autoid.ro/health`

Canonical API readiness check:

`https://mcp.autoid.ro/ready`

## Upgrade from v0.1.0 with systemd

Assuming the live application directory is `/opt/autoid-mcp`:

```bash
sudo systemctl stop autoid-mcp
sudo cp -a /opt/autoid-mcp /opt/autoid-mcp-backup-v0.1.0
sudo rm -rf /opt/autoid-mcp
sudo mkdir -p /opt/autoid-mcp
sudo cp -a ./autoid-mcp-v0.3.1/. /opt/autoid-mcp/
sudo cp /opt/autoid-mcp-backup-v0.1.0/.env /opt/autoid-mcp/.env
cd /opt/autoid-mcp
sudo npm install
sudo npm run smoke:api
sudo npm run build
sudo chown -R www-data:www-data /opt/autoid-mcp
sudo cp deploy/autoid-mcp.service /etc/systemd/system/autoid-mcp.service
sudo systemctl daemon-reload
sudo systemctl enable autoid-mcp
sudo systemctl restart autoid-mcp
sudo systemctl status autoid-mcp
```

Then verify:

```bash
curl -s https://mcp.autoid.ro/health
curl -s https://mcp.autoid.ro/ready
```

## Docker

The included Dockerfile intentionally uses `npm install` because this release archive does not include a generated lock file.

```bash
docker compose -f deploy/docker-compose.yml up -d --build
```

The container binds only to `127.0.0.1:3000`; expose it through the supplied Nginx reverse-proxy configuration.

## First MCP validation

After deployment, validate these tool calls in an MCP client:

```text
autoid_api_health({})
get_product_group({ model: "MC9300" })
list_product_variants({ model: "MC9300", availability: "available", limit: 20 })
get_product_offer({ sku: "MC930B-GSHDG4RW" })
get_related_products({ target: "MC9300", relation_type: "accessory", availability: "available", limit: 20 })
get_related_products({ target: "ZT610", relation_type: "consumable", category: "ribboane-imprimanta", availability: "available", limit: 20 })
get_related_products_summary({ target: "ZT610", relation_type: "consumable" })
```

## HestiaCP deployment note

If the host is managed by HestiaCP and a domain template already proxies `mcp.autoid.ro` to port `3000`, do not overwrite Hestia Nginx or Certbot configuration. Replace/build only the application files and restart the existing Node process through the host administrator's preferred supervisor.

## Security

v0.3.1 is read-only. It exposes no WordPress credentials and performs no writes. The canonical API remains the data and security boundary.

Before adding write tools such as RFQ creation, add authentication, authorization, audit logging and abuse controls separately.

## Public root

Opening `https://mcp.autoid.ro/` in a browser returns a small human landing page with links to `/health`, `/ready`, and `/mcp`. The Node process binds to `127.0.0.1:3000` and is intended to be published only through the existing HestiaCP/Nginx reverse proxy.


## Support Center tools — v0.3.1

The public endpoint `https://mcp.autoid.ro/mcp` now exposes the existing catalog tools plus three Support Center tools:

- `search_support` — search models, manuals, drivers, firmware, software, videos and troubleshooting resources.
- `fetch_support` — fetch one exact `model:<id>` or `resource:<id>` returned by search.
- `autoid_support_health` — verify the read-only Support Center source.

Support data is proxied from the existing first-party AutoID Support MCP source (`AUTOID_SUPPORT_MCP_URL`, default `https://www.autoid.ro/mcp/`). The Node service does not read WordPress SQL, filesystem or admin APIs. Product data continues to come from `AUTOID_API_BASE`.

`search_support` is intent-aware in v0.3.1: it merges the original query with model-wide and requested-resource-type searches, deduplicates results, and ranks requested types above generic resources. A multi-intent query such as `MC9300 firmware manual` should surface both the firmware/LifeGuard entry and the documentation/manual entry before unrelated generic resources.

For chat integrations, the recommended OpenAI Responses API configuration is one read-only remote MCP tool pointing to `https://mcp.autoid.ro/mcp`, with an explicit `allowed_tools` list and `require_approval: never`. Current price/stock questions should use `get_product_offer`; technical support resources should use `search_support` followed by `fetch_support`.
