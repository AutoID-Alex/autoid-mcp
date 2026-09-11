const DEFAULT_SUPPORT_MCP_URL = 'https://www.autoid.ro/mcp/';
const SUPPORT_PROTOCOL = '2026-07-28';
const USER_AGENT = 'AutoID-MCP/0.3.1';

export class SupportMcpError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
    public readonly details?: unknown,
  ) {
    super(message);
    this.name = 'SupportMcpError';
  }
}

export function supportMcpUrl(): string {
  return (process.env.AUTOID_SUPPORT_MCP_URL || DEFAULT_SUPPORT_MCP_URL).trim();
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function structuredFromToolResult(result: unknown): unknown {
  if (!isRecord(result)) return result;
  if (result.isError === true) {
    throw new SupportMcpError('AutoID Support MCP tool returned an error.', undefined, result);
  }
  if (isRecord(result.structuredContent)) return result.structuredContent;

  const content = Array.isArray(result.content) ? result.content : [];
  for (const item of content) {
    if (!isRecord(item) || item.type !== 'text' || typeof item.text !== 'string') continue;
    try {
      return JSON.parse(item.text);
    } catch {
      return { text: item.text };
    }
  }
  return result;
}

function resultRows(payload: unknown): Array<Record<string, unknown>> {
  if (!isRecord(payload) || !Array.isArray(payload.results)) return [];
  return payload.results.filter(isRecord);
}

function normalizeText(value: string): string {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase();
}

function compactText(value: string): string {
  return normalizeText(value).replace(/[^a-z0-9]+/g, '');
}

type SupportTopic =
  | 'firmware'
  | 'documentation'
  | 'driver'
  | 'software'
  | 'video'
  | 'troubleshooting'
  | 'setup'
  | 'datasheet'
  | 'release_notes'
  | 'battery';

const TOPIC_TERMS: Record<SupportTopic, string[]> = {
  firmware: ['firmware', 'lifeguard', 'os / firmware', 'downloads', 'printer os'],
  documentation: ['documentatie', 'documentation', 'manual', 'manual de utilizare', 'user guide', 'ghid'],
  driver: ['driver', 'drivere', 'windows driver', 'printer driver'],
  software: ['software', 'application software', 'aplicatie', 'aplicatii', 'utility', 'utilitar', 'sdk', 'developer'],
  video: ['video', 'videoclip', 'how-to', 'how to'],
  troubleshooting: ['depanare', 'troubleshooting', 'knowledge', 'eroare', 'problem'],
  setup: ['pornire', 'configurare', 'setup', 'getting started', 'quick start', 'initiala'],
  datasheet: ['datasheet', 'fisa tehnica', 'specificatii'],
  release_notes: ['release notes', 'note de versiune'],
  battery: ['baterie', 'battery'],
};

function requestedTopics(query: string): SupportTopic[] {
  const text = normalizeText(query);
  const checks: Array<[SupportTopic, RegExp]> = [
    ['firmware', /\b(?:firmware|lifeguard|printer\s+os)\b/],
    ['documentation', /\b(?:manual(?:e|ul)?|documenta[a-z]*|documentation|user\s+guide|ghid(?:uri|ul)?)\b/],
    ['driver', /\b(?:driver(?:e|ul)?)\b/],
    ['software', /\b(?:software|aplicati|utility|utilitar|sdk|developer)\b/],
    ['video', /\b(?:video|videoclip|how[ -]?to)\b/],
    ['troubleshooting', /\b(?:depan[a-z]*|troubleshoot[a-z]*|eroare|problem[a-z]*)\b/],
    ['setup', /\b(?:configur[a-z]*|instal[a-z]*|pornire|setup|quick\s+start|getting\s+started)\b/],
    ['datasheet', /\b(?:datasheet|fisa\s+tehnica|specificati)\b/],
    ['release_notes', /\b(?:release\s+notes|note\s+de\s+versiune)\b/],
    ['battery', /\b(?:baterie|battery)\b/],
  ];
  return checks.filter(([, rx]) => rx.test(text)).map(([topic]) => topic);
}

function fallbackSearchTokens(query: string): string[] {
  const stop = new Set([
    'pentru', 'despre', 'vreau', 'cauta', 'caut', 'driver', 'drivere', 'firmware',
    'software', 'manual', 'manuale', 'documentatie', 'documentație', 'documentation',
    'video', 'problema', 'problemă', 'eroare', 'support', 'suport', 'download',
    'descarcare', 'descărcare', 'aveti', 'aveți', 'este', 'sunt', 'dami', 'da-mi',
  ]);
  const raw = query.match(/[A-Za-z0-9][A-Za-z0-9._+\/-]{1,}/g) || [];
  const normalized = raw
    .map((token) => token.trim())
    .filter((token) => token.length >= 2 && !stop.has(token.toLowerCase()));
  const modelLike = normalized.filter((token) => /\d/.test(token));
  const others = normalized.filter((token) => !/\d/.test(token) && token.length >= 4);
  return [...new Set([...modelLike, ...others])].slice(0, 4);
}

function rowText(row: Record<string, unknown>): string {
  return normalizeText([
    typeof row.title === 'string' ? row.title : '',
    typeof row.display_title === 'string' ? row.display_title : '',
    typeof row.url === 'string' ? row.url : '',
    typeof row.display_url === 'string' ? row.display_url : '',
  ].join(' '));
}

function rowMatchesTopic(row: Record<string, unknown>, topic: SupportTopic): boolean {
  const text = rowText(row);
  return TOPIC_TERMS[topic].some((term) => text.includes(normalizeText(term)));
}

function scoreRow(
  row: Record<string, unknown>,
  query: string,
  modelTokens: string[],
  topics: SupportTopic[],
): number {
  const text = rowText(row);
  const compact = compactText(text);
  let score = 0;

  for (const token of modelTokens) {
    const needle = compactText(token);
    if (needle && compact.includes(needle)) score += /\d/.test(token) ? 90 : 25;
  }

  const queryWords = normalizeText(query).split(/[^a-z0-9]+/).filter((w) => w.length >= 4);
  for (const word of queryWords) if (text.includes(word)) score += 4;

  let matchedTopics = 0;
  for (const topic of topics) {
    if (rowMatchesTopic(row, topic)) {
      score += 120;
      matchedTopics += 1;
    }
  }
  if (topics.length > 0 && matchedTopics === 0) score -= 80;

  const id = typeof row.id === 'string' ? row.id : '';
  if (topics.length > 0 && id.startsWith('resource:')) score += 12;
  if (topics.length === 0 && id.startsWith('model:')) score += 18;

  if (!topics.includes('battery') && /\b(?:battery|baterie)\b/.test(text)) score -= 65;
  if (/centrul de (?:asistenta|cunostinte)|contactati serviciul|warranty|garantie/.test(text) && topics.length > 0) score -= 35;

  return score;
}

function rankAndDiversify(
  rows: Array<Record<string, unknown>>,
  query: string,
  modelTokens: string[],
  topics: SupportTopic[],
): Array<Record<string, unknown>> {
  const scored = rows
    .map((row, index) => ({ row, index, score: scoreRow(row, query, modelTokens, topics) }))
    .sort((a, b) => b.score - a.score || a.index - b.index);

  if (topics.length <= 1) return scored.map((item) => item.row).slice(0, 20);

  const picked = new Set<string>();
  const out: Array<Record<string, unknown>> = [];
  const keyFor = (row: Record<string, unknown>, i: number) =>
    typeof row.id === 'string' && row.id ? row.id : `row:${i}:${JSON.stringify(row)}`;

  for (const topic of topics) {
    const hit = scored.find((item, i) => rowMatchesTopic(item.row, topic) && !picked.has(keyFor(item.row, i)));
    if (!hit) continue;
    const key = typeof hit.row.id === 'string' && hit.row.id ? hit.row.id : JSON.stringify(hit.row);
    picked.add(key);
    out.push(hit.row);
  }

  for (const item of scored) {
    const key = typeof item.row.id === 'string' && item.row.id ? item.row.id : JSON.stringify(item.row);
    if (picked.has(key)) continue;
    picked.add(key);
    out.push(item.row);
    if (out.length >= 20) break;
  }
  return out.slice(0, 20);
}

export async function supportMcpSearch(query: string): Promise<unknown> {
  const topics = requestedTopics(query);
  const tokens = fallbackSearchTokens(query);
  const modelTokens = tokens.filter((token) => /\d/.test(token)).slice(0, 2);
  const attempted: string[] = [query.trim()];
  const merged = new Map<string, Record<string, unknown>>();

  const primaryPayload = await supportMcpCall('search', { query });
  for (const row of resultRows(primaryPayload)) {
    const id = typeof row.id === 'string' && row.id ? row.id : JSON.stringify(row);
    if (!merged.has(id)) merged.set(id, row);
  }

  const fallbackQueries = new Set<string>();
  for (const model of modelTokens) {
    fallbackQueries.add(model);
    for (const topic of topics.slice(0, 4)) {
      const label = topic === 'documentation' ? 'manual' : topic.replace('_', ' ');
      fallbackQueries.add(`${model} ${label}`);
    }
  }
  if (modelTokens.length === 0 && merged.size === 0) {
    for (const token of tokens.slice(0, 2)) fallbackQueries.add(token);
  }

  for (const candidate of [...fallbackQueries].filter((candidate) => candidate && candidate !== query.trim()).slice(0, 6)) {
    attempted.push(candidate);
    const payload = await supportMcpCall('search', { query: candidate });
    for (const row of resultRows(payload)) {
      const id = typeof row.id === 'string' && row.id ? row.id : JSON.stringify(row);
      if (!merged.has(id)) merged.set(id, row);
      if (merged.size >= 80) break;
    }
    if (merged.size >= 80) break;
  }

  if (merged.size === 0) return primaryPayload;

  const ranked = rankAndDiversify([...merged.values()], query, modelTokens, topics);
  return {
    results: ranked,
    search_strategy: attempted.length > 1 ? 'intent_aware_model_merge' : 'primary',
    original_query: query,
    query_analysis: {
      model_tokens: modelTokens,
      requested_topics: topics,
    },
    fallback_queries: attempted.slice(1),
  };
}

let requestSequence = 0;

export async function supportMcpCall(
  name: 'search' | 'fetch' | 'health',
  args: Record<string, unknown> = {},
): Promise<unknown> {
  const url = supportMcpUrl();
  const timeoutMs = Number(process.env.AUTOID_SUPPORT_MCP_TIMEOUT_MS || 15000);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const id = `autoid-support-${Date.now()}-${++requestSequence}`;

  const body = {
    jsonrpc: '2.0',
    id,
    method: 'tools/call',
    params: {
      name,
      arguments: args,
      _meta: {
        'io.modelcontextprotocol/protocolVersion': SUPPORT_PROTOCOL,
        'io.modelcontextprotocol/clientCapabilities': {},
      },
    },
  };

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'User-Agent': USER_AGENT,
        'MCP-Protocol-Version': SUPPORT_PROTOCOL,
        'Mcp-Method': 'tools/call',
        'Mcp-Name': name,
      },
      body: JSON.stringify(body),
      signal: controller.signal,
      cache: 'no-store',
    });

    const text = await response.text();
    let payload: unknown;
    try {
      payload = text ? JSON.parse(text) : null;
    } catch {
      throw new SupportMcpError(
        'AutoID Support MCP returned non-JSON data.',
        response.status,
        text.slice(0, 500),
      );
    }

    if (!response.ok) {
      throw new SupportMcpError(
        `AutoID Support MCP request failed with HTTP ${response.status}.`,
        response.status,
        payload,
      );
    }
    if (!isRecord(payload)) {
      throw new SupportMcpError('AutoID Support MCP returned an invalid JSON-RPC payload.');
    }
    if (isRecord(payload.error)) {
      throw new SupportMcpError(
        typeof payload.error.message === 'string' ? payload.error.message : 'AutoID Support MCP JSON-RPC error.',
        response.status,
        payload.error,
      );
    }
    return structuredFromToolResult(payload.result);
  } catch (error) {
    if (error instanceof SupportMcpError) throw error;
    if (error instanceof Error && error.name === 'AbortError') {
      throw new SupportMcpError(`AutoID Support MCP request timed out after ${timeoutMs} ms.`);
    }
    throw new SupportMcpError(
      error instanceof Error ? error.message : 'Unknown AutoID Support MCP error.',
    );
  } finally {
    clearTimeout(timer);
  }
}
