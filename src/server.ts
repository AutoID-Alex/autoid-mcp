import { createMcpHandler, McpServer } from '@modelcontextprotocol/server';
import { createMcpExpressApp } from '@modelcontextprotocol/express';
import { toNodeHandler } from '@modelcontextprotocol/node';
import * as z from 'zod/v4';
import { autoIdGet, apiBase, AutoIdApiError } from './autoid-api.js';
import { supportMcpCall, supportMcpSearch, supportMcpUrl, SupportMcpError } from './support-mcp.js';

const SERVER_NAME = 'autoid-products-support';
const SERVER_VERSION = '0.3.2';

const availabilitySchema = z
  .enum(['all', 'available', 'autoid', 'supplier', 'out_of_stock'])
  .default('available');

const relationTypeSchema = z
  .enum(['all', 'accessory', 'consumable', 'software', 'service_contract'])
  .default('all');

function toolResult(data: unknown) {
  return {
    content: [{ type: 'text' as const, text: JSON.stringify(data) }],
    structuredContent: data as Record<string, unknown>,
  };
}

function toolError(error: unknown) {
  const payload = error instanceof AutoIdApiError || error instanceof SupportMcpError
    ? {
        error: error.message,
        status: error.status ?? null,
        details: error.details ?? null,
      }
    : { error: error instanceof Error ? error.message : 'Unknown error' };

  return {
    isError: true,
    content: [{ type: 'text' as const, text: JSON.stringify(payload) }],
    structuredContent: payload,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/**
 * Compact projection of the canonical relations response.
 * No compatibility, price, stock or availability values are inferred or recalculated.
 */
function compactRelationSummary(payload: unknown): unknown {
  if (!isRecord(payload)) return payload;

  const resolution = isRecord(payload.resolution) ? payload.resolution : {};
  const rawCategories = isRecord(resolution.relation_categories)
    ? resolution.relation_categories
    : {};

  const relationCategories: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(rawCategories)) {
    if (!isRecord(value)) continue;
    relationCategories[key] = {
      found: value.found ?? null,
      relation_type: value.relation_type ?? key,
      relation: value.relation ?? null,
      inventory_policy: value.inventory_policy ?? null,
      term_id: value.term_id ?? null,
      name: value.name ?? null,
      slug: value.slug ?? null,
      descendant_count: value.descendant_count ?? null,
    };
  }

  return {
    schema_version: payload.schema_version ?? null,
    target: payload.target ?? null,
    source: {
      authority: 'AutoID canonical API',
      relation_evidence: resolution.accepted_evidence ?? null,
      source_taxonomy: resolution.source_taxonomy ?? null,
      generic_tags_are_used: resolution.generic_tags_are_used ?? null,
    },
    relation_categories: relationCategories,
    filter: payload.filter ?? null,
    summary: payload.summary ?? null,
    pagination: payload.pagination ?? null,
    rules: payload.rules ?? null,
    diagnostics: payload.diagnostics ?? null,
    freshness: payload.freshness ?? null,
    items_omitted: true,
    note:
      'Summary projection only. Call get_related_products for catalog items. Out-of-stock items are intentionally not returned unless explicitly requested.',
  };
}

function buildServer() {
  const server = new McpServer({
    name: SERVER_NAME,
    version: SERVER_VERSION,
  });

  server.registerTool(
    'search_products',
    {
      title: 'Search AutoID products',
      description:
        'Search the official AutoID catalog by model, SKU or text. Use this first when the exact SKU is unknown. Results come from the first-party AutoID canonical API. Prefer exact product groups and SKUs over loosely related resources. Customer-facing RON prices are exposed under pricing.ron_display when available; prefer the inc-VAT value for Romanian storefront answers and never convert EUR yourself.',
      inputSchema: z.object({
        query: z
          .string()
          .min(1)
          .describe('Model, SKU or product search text, for example MC9300 or ZT610.'),
        limit: z.number().int().min(1).max(100).default(20),
      }),
    },
    async ({ query, limit }) => {
      try {
        return toolResult(await autoIdGet('/search', { q: query, limit }));
      } catch (error) {
        return toolError(error);
      }
    },
  );

  server.registerTool(
    'list_product_groups',
    {
      title: 'List AutoID product groups',
      description:
        'Enumerates canonical grouped-product models for exhaustive catalog synchronization. This is a discovery tool, not search: clients should page through the complete result set using limit and offset. Results come only from the first-party AutoID canonical API and must not be reconstructed from search queries.',
      inputSchema: z.object({
        limit: z.number().int().min(1).max(500).default(100),
        offset: z.number().int().min(0).default(0),
        brand: z.string().min(1).max(120).optional(),
        lifecycle: z.enum(['active', 'discontinued', 'all']).default('all'),
      }),
    },
    async ({ limit, offset, brand, lifecycle }) => {
      try {
        return toolResult(
          await autoIdGet('/product-groups', {
            limit,
            offset,
            brand,
            lifecycle,
          }),
        );
      } catch (error) {
        return toolError(error);
      }
    },
  );

  server.registerTool(
    'list_products',
    {
      title: 'List all AutoID products',
      description:
        'Exhaustive read-only product registry for catalog synchronization. Pages through every published WooCommerce product, including grouped models and standalone/exact products. Use entity_type=grouped or single to filter without approximating completeness from search.',
      inputSchema: z.object({
        limit: z.number().int().min(1).max(500).default(250),
        offset: z.number().int().min(0).default(0),
        entity_type: z.enum(['all', 'grouped', 'single']).default('all'),
      }),
    },
    async ({ limit, offset, entity_type }) => {
      try {
        return toolResult(await autoIdGet('/products', { limit, offset, entity_type }));
      } catch (error) {
        return toolError(error);
      }
    },
  );

  server.registerTool(
    'list_brands',
    {
      title: 'List AutoID brands',
      description:
        'Returns the complete canonical WooCommerce brand/manufacturer taxonomy used by AutoID. This taxonomy is authoritative for brand archives and is never inferred from product titles.',
      inputSchema: z.object({}),
    },
    async () => {
      try {
        return toolResult(await autoIdGet('/brands'));
      } catch (error) {
        return toolError(error);
      }
    },
  );

  server.registerTool(
    'list_categories',
    {
      title: 'List AutoID product categories',
      description:
        'Returns the complete canonical WooCommerce product_cat taxonomy with parent/depth/path data for category archives and catalog filters.',
      inputSchema: z.object({}),
    },
    async () => {
      try {
        return toolResult(await autoIdGet('/categories'));
      } catch (error) {
        return toolError(error);
      }
    },
  );

  server.registerTool(
    'get_product_group',
    {
      title: 'Get AutoID product group',
      description:
        'Returns authoritative grouped-product information for an AutoID model such as MC9300. Group prices are FROM prices, not exact SKU prices. Distinguish catalog_from from available_from; available_from only considers members with stock_autoid > 0 or stock_distributie > 0. Customer-facing RON display prices are exposed by the canonical API under pricing.ron_display; they are WooCommerce display/validation values, not the commercial authority.',
      inputSchema: z.object({
        model: z.string().min(1).describe('Grouped product SKU/model, for example MC9300.'),
      }),
    },
    async ({ model }) => {
      try {
        return toolResult(await autoIdGet(`/product-groups/${encodeURIComponent(model)}`));
      } catch (error) {
        return toolError(error);
      }
    },
  );

  server.registerTool(
    'list_product_variants',
    {
      title: 'List AutoID product variants',
      description:
        'Lists exact SKUs belonging to an AutoID grouped product. Default availability=available. AutoID stock is prioritized before distribution-only stock. Use availability=all only when the user explicitly needs unavailable configurations too. Each returned commercial card can expose pricing.ron_display with ex-VAT and inc-VAT WooCommerce RON values.',
      inputSchema: z.object({
        model: z.string().min(1).describe('Grouped product SKU/model, for example MC9300.'),
        availability: availabilitySchema,
        limit: z.number().int().min(1).max(500).default(100),
        offset: z.number().int().min(0).default(0),
      }),
    },
    async ({ model, availability, limit, offset }) => {
      try {
        return toolResult(
          await autoIdGet(`/product-groups/${encodeURIComponent(model)}/variants`, {
            availability,
            limit,
            offset,
          }),
        );
      } catch (error) {
        return toolError(error);
      }
    },
  );

  server.registerTool(
    'get_product',
    {
      title: 'Get exact AutoID SKU',
      description:
        'Returns canonical data for an exact AutoID SKU. Use this for product identity and stable product data. For current price, stock or delivery availability, always call get_product_offer as well. The canonical product payload exposes WooCommerce RON display values separately from authoritative EUR metadata.',
      inputSchema: z.object({
        sku: z.string().min(1).describe('Exact AutoID product SKU.'),
      }),
    },
    async ({ sku }) => {
      try {
        return toolResult(await autoIdGet(`/products/${encodeURIComponent(sku)}`));
      } catch (error) {
        return toolError(error);
      }
    },
  );

  server.registerTool(
    'get_product_offer',
    {
      title: 'Get live AutoID price and stock',
      description:
        'Returns the current authoritative AutoID offer for an exact SKU. ALWAYS use this tool before answering current price, stock, availability or delivery questions. pret_lista and pret_autoid_euro are authoritative EUR ex-VAT price sources; stock_autoid and stock_distributie are authoritative stock sources. For Romanian customer-facing output, use price.ron_display and prefer the inc-VAT value; RON comes from WooCommerce _regular_price/_sale_price and is display/validation data, not the commercial authority. Do not convert EUR yourself and do not infer availability from cached descriptions or WooCommerce sale-price presence.',
      inputSchema: z.object({
        sku: z.string().min(1).describe('Exact AutoID product SKU.'),
      }),
    },
    async ({ sku }) => {
      try {
        return toolResult(await autoIdGet(`/offers/${encodeURIComponent(sku)}`));
      } catch (error) {
        return toolError(error);
      }
    },
  );

  server.registerTool(
    'get_related_products',
    {
      title: 'Get compatible AutoID related products',
      description:
        'Returns first-party related catalog entities for a model or exact SKU. Compatibility evidence comes only from product_tag; relation type comes from WooCommerce product_cat. Supported relation types: accessory, consumable, software, service_contract, or all. For accessory and consumable, default availability=available means stock_autoid > 0 OR stock_distributie > 0; results with AutoID stock are prioritized before distribution-only results. Out-of-stock products are extra catalog information and are omitted by default: request availability=out_of_stock or availability=all explicitly if needed. Software and service contracts are not stock-managed and remain eligible with availability=available. Returned commercial cards expose pricing.ron_display when WooCommerce RON pricing exists; prefer inc-VAT for Romanian customer-facing answers. Use category with an exact WooCommerce category slug to narrow large sets, for example ribboane-imprimanta, role-de-etichete or intretinere-imprimante.',
      inputSchema: z.object({
        target: z
          .string()
          .min(1)
          .describe('AutoID model/group SKU or exact product SKU, for example ZT610 or MC930B-GSHDG4RW.'),
        relation_type: relationTypeSchema,
        availability: availabilitySchema,
        category: z
          .string()
          .min(1)
          .optional()
          .describe('Optional exact WooCommerce product_cat slug used as a deterministic filter.'),
        limit: z
          .number()
          .int()
          .min(1)
          .max(200)
          .default(30)
          .describe('Keep this small for MCP context. Use pagination rather than requesting huge result sets.'),
        offset: z.number().int().min(0).default(0),
      }),
    },
    async ({ target, relation_type, availability, category, limit, offset }) => {
      try {
        return toolResult(
          await autoIdGet(`/relations/${encodeURIComponent(target)}`, {
            relation_type,
            availability,
            category,
            limit,
            offset,
          }),
        );
      } catch (error) {
        return toolError(error);
      }
    },
  );

  server.registerTool(
    'get_related_products_summary',
    {
      title: 'Summarize all AutoID related products',
      description:
        'Returns a compact catalog summary for related products without sending the full item list into MCP context. Use this when the user asks how many compatible products exist in total, wants the count of out-of-stock compatible consumables/accessories, or needs relation-type counts. This summary deliberately queries availability=all, while get_related_products defaults to available. Do not use it as a substitute for get_product_offer when current commercial details for one exact SKU are needed.',
      inputSchema: z.object({
        target: z
          .string()
          .min(1)
          .describe('AutoID model/group SKU or exact product SKU.'),
        relation_type: relationTypeSchema,
        category: z
          .string()
          .min(1)
          .optional()
          .describe('Optional exact WooCommerce product_cat slug.'),
      }),
    },
    async ({ target, relation_type, category }) => {
      try {
        const payload = await autoIdGet(`/relations/${encodeURIComponent(target)}`, {
          relation_type,
          availability: 'all',
          category,
          limit: 1,
          offset: 0,
        });
        return toolResult(compactRelationSummary(payload));
      } catch (error) {
        return toolError(error);
      }
    },
  );

  server.registerTool(
    'search_support',
    {
      title: 'Search AutoID technical support',
      description:
        'Search the official AutoID Support Center for a model, manual, driver, firmware, software, troubleshooting article, video or other verified technical resource. The search layer is intent-aware: model-wide and resource-type matches are merged and ranked so requested resource types outrank generic resources. Use this before fetch_support and fetch every resource you rely on. Search results are read-only first-party AutoID support records and manufacturer resources; do not infer a firmware version or procedure from a title alone.',
      inputSchema: z.object({
        query: z
          .string()
          .min(1)
          .max(500)
          .describe('Support search text, model, SKU, problem or resource type; for example MC9300 firmware or ZT610 driver.'),
      }),
    },
    async ({ query }) => {
      try {
        return toolResult(await supportMcpSearch(query));
      } catch (error) {
        return toolError(error);
      }
    },
  );

  server.registerTool(
    'fetch_support',
    {
      title: 'Fetch AutoID support model or resource',
      description:
        'Fetch the full verified text and metadata for one result returned by search_support. IDs have the form model:<id> or resource:<id>. Use the returned verified text, warnings, model scope, official URL, version/OS metadata and source provenance as the grounding source for technical answers. Never substitute a nearby model or invent missing versions.',
      inputSchema: z.object({
        id: z
          .string()
          .regex(/^(model|resource):\d+$/)
          .describe('Exact result ID from search_support, for example model:1600 or resource:231582.'),
      }),
    },
    async ({ id }) => {
      try {
        return toolResult(await supportMcpCall('fetch', { id }));
      } catch (error) {
        return toolError(error);
      }
    },
  );

  server.registerTool(
    'autoid_support_health',
    {
      title: 'Check AutoID Support MCP health',
      description:
        'Checks the read-only AutoID Support Center MCP source used for manuals, firmware, drivers, software, videos and troubleshooting resources.',
      inputSchema: z.object({}),
    },
    async () => {
      try {
        return toolResult(await supportMcpCall('health'));
      } catch (error) {
        return toolError(error);
      }
    },
  );

  server.registerTool(
    'autoid_api_health',
    {
      title: 'Check AutoID canonical API health',
      description:
        'Checks whether the first-party AutoID canonical API is reachable and reports its declared authoritative commercial fields and relation capabilities.',
      inputSchema: z.object({}),
    },
    async () => {
      try {
        return toolResult(await autoIdGet('/health'));
      } catch (error) {
        return toolError(error);
      }
    },
  );

  return server;
}

const handler = createMcpHandler(buildServer);
const nodeHandler = toNodeHandler(handler);

const publicHost = process.env.MCP_PUBLIC_HOST || 'mcp.autoid.ro';
const app = createMcpExpressApp({
  host: '0.0.0.0',
  allowedHosts: [publicHost, 'localhost', '127.0.0.1'],
});

app.get('/', (_req, res) => {
  res.status(200);
  res.setHeader('Content-Type', 'text/html; charset=utf-8');
  res.setHeader('Cache-Control', 'no-store');
  res.setHeader('X-Robots-Tag', 'noindex, nofollow');
  res.send(`<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AutoID MCP Server</title>
  <style>
    :root { color-scheme: light dark; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    body { margin: 0; min-height: 100vh; display: grid; place-items: center; background: #f5f6f8; color: #17191c; }
    main { width: min(760px, calc(100% - 32px)); background: #fff; border: 1px solid #e4e7eb; border-radius: 18px; box-shadow: 0 18px 50px rgba(0,0,0,.08); padding: 32px; }
    h1 { margin: 0 0 8px; font-size: 30px; }
    p { margin: 8px 0; line-height: 1.6; color: #4d5560; }
    .status { display: inline-flex; align-items: center; gap: 8px; font-weight: 700; margin: 14px 0 20px; }
    .dot { width: 10px; height: 10px; border-radius: 999px; background: #1f9d55; box-shadow: 0 0 0 4px rgba(31,157,85,.12); }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 12px; margin-top: 22px; }
    a, .card { display: block; padding: 14px 16px; border: 1px solid #e4e7eb; border-radius: 12px; text-decoration: none; color: #17191c; font-weight: 700; }
    a small, .card small { display: block; margin-top: 4px; color: #707985; font-weight: 500; }
    code { background: #f1f3f5; padding: 2px 6px; border-radius: 6px; }
    footer { margin-top: 24px; font-size: 13px; color: #7a838d; }
    @media (prefers-color-scheme: dark) {
      body { background: #111418; color: #f5f7fa; }
      main { background: #181c21; border-color: #2c333b; box-shadow: none; }
      p, footer { color: #aeb7c2; }
      a, .card { color: #f5f7fa; border-color: #2c333b; }
      a small, .card small { color: #98a2ad; }
      code { background: #232930; }
    }
  </style>
</head>
<body>
  <main>
    <h1>AutoID MCP Server</h1>
    <p>Read-only Model Context Protocol gateway for official AutoID catalog, live offer, compatibility and technical support data.</p>
    <div class="status"><span class="dot"></span>Service online · v${SERVER_VERSION}</div>
    <p>MCP clients should connect to <code>https://${publicHost}/mcp</code>.</p>
    <div class="grid">
      <a href="/health">Health<small>Service capabilities and policies</small></a>
      <a href="/ready">Readiness<small>Checks the canonical AutoID API</small></a>
      <div class="card">MCP endpoint <code>/mcp</code><small>Streamable HTTP transport for MCP clients</small></div>
    </div>
    <footer>AutoID · read-only first-party catalog + technical support data · no direct database access</footer>
  </main>
</body>
</html>`);
});

app.get('/favicon.ico', (_req, res) => res.status(204).end());

app.get('/health', (_req, res) => {
  res.json({
    service: 'AutoID MCP Server',
    status: 'ok',
    version: SERVER_VERSION,
    canonical_api: apiBase(),
    support_mcp_source: supportMcpUrl(),
    read_only: true,
    mcp_endpoint: '/mcp',
    readiness_endpoint: '/ready',
    capabilities: {
      products: true,
      product_group_discovery: true,
      full_product_discovery: true,
      taxonomy_archives: true,
      offers: true,
      variants: true,
      relations: true,
      ron_display_pricing: true,
      support_center: true,
      support_tools: ['search_support', 'fetch_support', 'autoid_support_health'],
      relation_types: ['accessory', 'consumable', 'software', 'service_contract'],
    },
    policies: {
      stocked_relation_default: 'available',
      stock_priority: ['stock_autoid', 'stock_distributie', 'out_of_stock_explicit_only'],
      non_stock_managed_relations: ['software', 'service_contract'],
      relation_evidence: 'product_tag only; product_cat determines relation type',
      customer_price_display: 'RON inc VAT via canonical pricing.ron_display / price.ron_display',
      ron_display_role: 'WooCommerce display/validation; EUR metadata remains commercial authority',
      support_grounding: 'search_support -> fetch_support; manufacturer/AutoID source metadata remains authoritative',
      catalog_discovery: 'list_products for exhaustive catalog; list_product_groups for grouped-only discovery; never approximate completeness with search queries',
    },
  });
});

app.get('/ready', async (_req, res) => {
  try {
    const [canonicalHealth, supportHealth] = await Promise.all([
      autoIdGet('/health'),
      supportMcpCall('health'),
    ]);
    res.status(200).json({
      service: 'AutoID MCP Server',
      status: 'ready',
      version: SERVER_VERSION,
      canonical_api: apiBase(),
      support_mcp_source: supportMcpUrl(),
      canonical_api_health: canonicalHealth,
      support_mcp_health: supportHealth,
    });
  } catch (error) {
    const details = error instanceof AutoIdApiError || error instanceof SupportMcpError
      ? { message: error.message, status: error.status ?? null }
      : { message: error instanceof Error ? error.message : 'Unknown error' };
    res.status(503).json({
      service: 'AutoID MCP Server',
      status: 'not_ready',
      version: SERVER_VERSION,
      canonical_api: apiBase(),
      support_mcp_source: supportMcpUrl(),
      error: details,
    });
  }
});

app.all('/mcp', (req, res) => void nodeHandler(req, res, req.body));

const port = Number(process.env.PORT || 3000);
app.listen(port, '127.0.0.1', () => {
  console.log(`AutoID MCP v${SERVER_VERSION} listening on http://127.0.0.1:${port}`);
  console.log('MCP endpoint: /mcp');
  console.log('Readiness endpoint: /ready');
  console.log(`Canonical API: ${apiBase()}`);
  console.log(`Support MCP source: ${supportMcpUrl()}`);
});
