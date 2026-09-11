# Publishing to the Official MCP Registry

This repository describes the remote AutoID MCP server. The actual MCP service remains hosted at:

```text
https://mcp.autoid.ro/mcp
```

The official registry entry is configured in `server.json` as:

```text
ro.autoid/autoid-support
```

This uses the reverse-DNS namespace for `autoid.ro`, so the registry requires domain authentication before publication.

## Important

Never commit a registry private key, API key, access token or WordPress secret to this repository.

## Recommended flow

1. Push this repository to GitHub.
2. Let the included validation workflow validate `server.json`.
3. Set up MCP Registry HTTP or DNS authentication for `autoid.ro`.
4. Install/download the official `mcp-publisher` CLI.
5. Authenticate with the domain method.
6. Run validation.
7. Publish `server.json`.
8. Verify the registry entry.

The exact authentication command depends on whether HTTP or DNS domain verification is selected. Configure that only after the public verification record/key is in place.

## Validate locally

Once `mcp-publisher` is installed:

```text
mcp-publisher validate server.json
```

## Publish

After successful domain authentication:

```text
mcp-publisher publish server.json
```

## New MCP versions

When the remote MCP version changes, update the `version` field in `server.json`, commit the change and publish that new version to the registry.
