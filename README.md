# AutoID Product Catalog & Support MCP

<!-- mcp-name: ro.autoid/autoid-support -->

Official read-only Model Context Protocol (MCP) endpoint for **AutoID Romania**.

The server gives AI agents structured access to AutoID product catalog and support data without direct database access.

## Remote MCP endpoint

```text
https://mcp.autoid.ro/mcp
```

Transport: **Streamable HTTP**  
Access: **Public, read-only**

## What agents can do

- Search AutoID products, models and exact SKUs.
- Read live AutoID and distributor stock.
- Read current commercial pricing from the canonical AutoID product API.
- List grouped-product variants and exact configurations.
- Filter product variants using structured WooCommerce technical attributes.
- Find accessories, consumables, software and service relationships.
- Search verified AutoID Support Center resources.
- Fetch manuals, firmware, drivers and other technical resources.

## Example questions

```text
Find a Zebra ZT610 600 dpi printer with Ethernet.

Which printheads are available for CAB SQUIX 2?

Is MC930B-GSHDG4RW in stock and what is the current price?

Find the official firmware and manual for Zebra MC9300.
```

## Data authority

The MCP server is an interface layer. It does not infer missing product data and does not query WordPress SQL directly.

```text
AI agent / MCP client
        |
        v
https://mcp.autoid.ro/mcp
        |
        +--> AutoID Canonical Product API
        |    https://www.autoid.ro/wp-json/autoid-ai/v1/
        |
        +--> AutoID Support Center
             https://www.autoid.ro/support/
```

Commercial price authority is the AutoID canonical product source. Stock is read from the current AutoID and distribution stock fields. Technical product constraints use structured WooCommerce attributes where available. Missing values remain unknown rather than being guessed.

## Discovery

- Website: https://www.autoid.ro/
- MCP homepage: https://mcp.autoid.ro/
- MCP endpoint: https://mcp.autoid.ro/mcp
- MCP health: https://mcp.autoid.ro/health
- MCP readiness: https://mcp.autoid.ro/ready
- llms.txt: https://www.autoid.ro/llms.txt
- Support llms.txt: https://www.autoid.ro/support/llms.txt

## Tools

The current public MCP exposes 11 read-only tools. See [docs/TOOLS.md](docs/TOOLS.md).

## Official MCP Registry

Registry metadata is stored in [`server.json`](server.json).

The intended official registry identity is:

```text
ro.autoid/autoid-support
```

Because this is a domain-based namespace, publishing requires verification of control over `autoid.ro`. See [PUBLISHING.md](PUBLISHING.md).

## Security

Do not open issues containing API keys, WordPress credentials, access tokens, private customer data or internal secrets. See [SECURITY.md](SECURITY.md).
