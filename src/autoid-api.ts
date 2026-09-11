const DEFAULT_BASE = 'https://www.autoid.ro/wp-json/autoid-ai/v1';
const USER_AGENT = 'AutoID-MCP/0.3.1';

export class AutoIdApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
    public readonly details?: unknown,
  ) {
    super(message);
    this.name = 'AutoIdApiError';
  }
}

export function apiBase(): string {
  return (process.env.AUTOID_API_BASE || DEFAULT_BASE).replace(/\/$/, '');
}

export async function autoIdGet(
  path: string,
  query?: Record<string, string | number | boolean | undefined>,
): Promise<unknown> {
  const url = new URL(`${apiBase()}${path.startsWith('/') ? path : `/${path}`}`);

  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined) url.searchParams.set(key, String(value));
    }
  }

  const timeoutMs = Number(process.env.AUTOID_API_TIMEOUT_MS || 15000);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        Accept: 'application/json',
        'User-Agent': USER_AGENT,
      },
      signal: controller.signal,
      cache: 'no-store',
    });

    const text = await response.text();
    let body: unknown;
    try {
      body = text ? JSON.parse(text) : null;
    } catch {
      throw new AutoIdApiError(
        'AutoID API returned non-JSON data.',
        response.status,
        text.slice(0, 500),
      );
    }

    if (!response.ok) {
      throw new AutoIdApiError(
        `AutoID API request failed with HTTP ${response.status}.`,
        response.status,
        body,
      );
    }

    return body;
  } catch (error) {
    if (error instanceof AutoIdApiError) throw error;
    if (error instanceof Error && error.name === 'AbortError') {
      throw new AutoIdApiError(`AutoID API request timed out after ${timeoutMs} ms.`);
    }
    throw new AutoIdApiError(
      error instanceof Error ? error.message : 'Unknown AutoID API error.',
    );
  } finally {
    clearTimeout(timer);
  }
}
