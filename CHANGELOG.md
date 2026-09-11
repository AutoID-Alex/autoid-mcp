# Changelog

## 0.3.1 — 2026-09-10
- Support search is now intent-aware and model-aware.
- Multi-intent queries such as `MC9300 firmware manual` merge model-wide and resource-type searches instead of accepting the first generic result.
- Requested resource types are ranked above generic knowledge-base/battery resources unless those generic topics were requested.
- Added a smoke assertion that MC9300 firmware and documentation are both surfaced by the unified Support search.
- Keeps `search_support`, `fetch_support` and `autoid_support_health` read-only over the existing first-party AutoID Support MCP source.
- No dependency, HestiaCP, Nginx, TLS, canonical product API or pricing changes.

## 0.2.1 - 2026-09-10

- Adds a human-friendly landing page at `/` instead of Express `Cannot GET /`.
- Binds the Node listener to `127.0.0.1:3000` for HestiaCP/Nginx reverse-proxy deployments instead of exposing the app on all interfaces.
- Adds explicit MCP guidance for customer-facing RON prices exposed by canonical API v0.3.9.
- Search, variants and related-product tool descriptions now direct agents to `pricing.ron_display`.
- Exact live-offer guidance now directs Romanian customer-facing answers to `price.ron_display` and prefers inc-VAT values.
- Keeps EUR `pret_lista` / `pret_autoid_euro` as commercial authority; MCP must not derive RON via FX conversion.
- `/health` advertises RON display pricing capability and authority semantics.
- Smoke test now verifies RON display pricing on search, grouped products, variants, ZT610 consumables and exact offers.
- No dependency changes; existing v0.2.0 `node_modules` can be reused for build/restart.

## 0.2.0 - 2026-09-10

- Added `get_related_products` over `/relations/{sku-or-model}`.
- Added relation types: `accessory`, `consumable`, `software`, `service_contract`, `all`.
- Compatibility evidence remains first-party `product_tag`; relation class is determined by WooCommerce `product_cat`.
- Stocked relations (`accessory`, `consumable`) default to `availability=available`.
- AutoID stock is prioritized before distribution-only stock by the canonical API.
- Out-of-stock related products are omitted by default and require explicit `availability=out_of_stock` or `all`.
- Added `get_related_products_summary` to expose total/out-of-stock catalog counts without returning the full item list.
- Software and service contracts are handled as `not_stock_managed`.
- Added category slug filtering for large consumable/accessory result sets.
- Added `/ready` HTTP readiness endpoint that verifies the canonical API.
- Added `npm run smoke:api` canonical API validation script.
- Increased default canonical API timeout to 15 seconds for large relation queries.
- Fixed Docker build for archives without `package-lock.json` by using `npm install` instead of `npm ci`.

Validated before release against AutoID canonical API plugin v0.3.8 using MC9300 and ZT610 relation datasets.
