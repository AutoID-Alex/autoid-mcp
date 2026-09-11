const base = (process.env.AUTOID_API_BASE || 'https://www.autoid.ro/wp-json/autoid-ai/v1').replace(/\/$/, '');
const timeoutMs = Number(process.env.AUTOID_API_TIMEOUT_MS || 15000);

async function get(path) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${base}${path}`, {
      headers: { Accept: 'application/json', 'User-Agent': 'AutoID-MCP-Smoke/0.3.1' },
      signal: controller.signal,
      cache: 'no-store',
    });
    const text = await response.text();
    let body;
    try {
      body = JSON.parse(text);
    } catch {
      throw new Error(`${path}: non-JSON response (${response.status}) ${text.slice(0, 180)}`);
    }
    if (!response.ok) {
      throw new Error(`${path}: HTTP ${response.status} ${JSON.stringify(body).slice(0, 250)}`);
    }
    return body;
  } finally {
    clearTimeout(timer);
  }
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

console.log(`Testing canonical API: ${base}`);

const health = await get('/health');
assert(health?.status === 'ok', 'Canonical API health is not ok.');
assert(health?.display_pricing?.currency === 'RON', 'Canonical API does not advertise RON display pricing. Install/upgrade AutoID AI Data Inspector v0.3.9+ first.');
console.log(`OK health: plugin ${health?.plugin_version ?? 'unknown'}, schema ${health?.schema_version ?? 'unknown'} + RON display`);

const search = await get('/search?q=MC9300&limit=2');
assert(search?.best_match?.sku === 'MC9300', 'MC9300 search best match did not resolve.');
assert(search?.best_match?.pricing?.ron_display?.currency === 'RON', 'Search best-match RON display pricing is missing.');
assert(search?.items?.[1]?.pricing?.ron_display?.currency === 'RON', 'Search exact-SKU RON display pricing is missing.');
console.log('OK search: MC9300 + RON display');

const mcGroup = await get('/product-groups/MC9300');
assert(mcGroup?.product?.sku === 'MC9300', 'MC9300 product group did not resolve as expected.');
assert(mcGroup?.pricing?.ron_display?.currency === 'RON', 'MC9300 group RON display pricing is missing.');
console.log('OK product group: MC9300 + RON display');

const mcVariants = await get('/product-groups/MC9300/variants?availability=available&limit=1');
assert((mcVariants?.pagination?.total ?? mcVariants?.summary?.total ?? 0) > 0, 'MC9300 has no available variants in smoke test.');
assert(mcVariants?.items?.[0]?.pricing?.ron_display?.currency === 'RON', 'Variant RON display pricing is missing.');
console.log(`OK variants: available total ${mcVariants?.pagination?.total ?? mcVariants?.summary?.total ?? 'unknown'} + RON display`);

const mcRelations = await get('/relations/MC9300?relation_type=all&availability=available&limit=1');
assert(String(mcRelations?.schema_version ?? '').startsWith('autoid-relations/'), 'MC9300 relations schema missing.');
console.log(`OK MC9300 relations: available total ${mcRelations?.summary?.total ?? 'unknown'}`);

const ztConsumables = await get('/relations/ZT610?relation_type=consumable&availability=available&limit=1');
assert((ztConsumables?.summary?.by_relation_type?.consumable?.total ?? 0) > 0, 'ZT610 has no available consumables in smoke test.');
assert(ztConsumables?.items?.[0]?.pricing?.ron_display?.currency === 'RON', 'ZT610 consumable RON display pricing is missing.');
console.log(`OK ZT610 consumables: available total ${ztConsumables?.summary?.by_relation_type?.consumable?.total ?? 'unknown'} + RON display`);

const offer = await get('/offers/MC930B-GSHDG4RW');
assert(offer?.product?.sku === 'MC930B-GSHDG4RW' || offer?.sku === 'MC930B-GSHDG4RW', 'Exact offer smoke test did not resolve the expected SKU.');
assert(offer?.price?.ron_display?.currency === 'RON', 'Exact offer RON display pricing is missing.');
assert((offer?.price?.ron_display?.autoid_inc_vat ?? 0) > 0, 'Exact offer RON inc-VAT AutoID price is missing.');
console.log('OK exact offer: MC930B-GSHDG4RW + RON inc VAT');

console.log('Canonical API smoke test passed.');

const supportMcpUrl = process.env.AUTOID_SUPPORT_MCP_URL || 'https://www.autoid.ro/mcp/';
const supportProtocol = '2026-07-28';
let supportSeq = 0;

async function supportCall(name, args = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), Number(process.env.AUTOID_SUPPORT_MCP_TIMEOUT_MS || 15000));
  const id = `smoke-${Date.now()}-${++supportSeq}`;
  try {
    const response = await fetch(supportMcpUrl, {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'User-Agent': 'AutoID-MCP-Smoke/0.3.1',
        'MCP-Protocol-Version': supportProtocol,
        'Mcp-Method': 'tools/call',
        'Mcp-Name': name,
      },
      body: JSON.stringify({
        jsonrpc: '2.0',
        id,
        method: 'tools/call',
        params: {
          name,
          arguments: args,
          _meta: {
            'io.modelcontextprotocol/protocolVersion': supportProtocol,
            'io.modelcontextprotocol/clientCapabilities': {},
          },
        },
      }),
      signal: controller.signal,
      cache: 'no-store',
    });
    const text = await response.text();
    let payload;
    try { payload = JSON.parse(text); }
    catch { throw new Error(`Support MCP ${name}: non-JSON response (${response.status}) ${text.slice(0, 180)}`); }
    if (!response.ok || payload?.error) throw new Error(`Support MCP ${name}: HTTP ${response.status} ${JSON.stringify(payload).slice(0, 300)}`);
    const result = payload?.result;
    if (result?.isError) throw new Error(`Support MCP ${name}: tool error ${JSON.stringify(result).slice(0, 300)}`);
    return result?.structuredContent ?? result;
  } finally {
    clearTimeout(timer);
  }
}

console.log(`Testing Support MCP source: ${supportMcpUrl}`);
const supportHealth = await supportCall('health');
assert(supportHealth?.status === 'ok', 'Support MCP health is not ok.');
console.log(`OK support health: plugin ${supportHealth?.plugin_version ?? 'unknown'}, protocol ${supportHealth?.protocol ?? 'unknown'}`);

const supportSearch = await supportCall('search', { query: 'MC9300' });
const supportResults = Array.isArray(supportSearch?.results) ? supportSearch.results : [];
assert(supportResults.length > 0, 'Support MCP search returned no MC9300 results.');
const supportModel = supportResults.find((row) => String(row?.id || '').startsWith('model:')) || supportResults[0];
assert(supportModel?.id, 'Support MCP search result has no id.');
console.log(`OK support search: ${supportResults.length} result(s), first usable id ${supportModel.id}`);

const supportFetch = await supportCall('fetch', { id: supportModel.id });
assert(supportFetch?.id === supportModel.id, 'Support MCP fetch did not return the requested id.');
assert(typeof supportFetch?.text === 'string' && supportFetch.text.length > 20, 'Support MCP fetch returned no usable text.');
console.log(`OK support fetch: ${supportFetch.id}`);

console.log('AutoID product + Support MCP smoke test passed.');

// Validate the unified intent-aware Support search wrapper built in dist/.
const { supportMcpSearch } = await import('../dist/support-mcp.js');
const multiSupport = await supportMcpSearch('MC9300 firmware manual');
const multiRows = Array.isArray(multiSupport?.results) ? multiSupport.results : [];
const multiTitles = multiRows.map((row) => String(row?.title || row?.display_title || '').toLowerCase());
assert(multiRows.length > 0, 'Intent-aware Support search returned no MC9300 results.');
assert(multiTitles.some((title) => title.includes('firmware') || title.includes('lifeguard')), 'Intent-aware Support search did not surface MC9300 firmware/LifeGuard.');
assert(multiTitles.some((title) => title.includes('documenta') || title.includes('manual')), 'Intent-aware Support search did not surface MC9300 documentation/manual.');
console.log('OK intent-aware support search: firmware + manual surfaced for MC9300');
console.log('AutoID MCP v0.3.1 smoke test passed.');
