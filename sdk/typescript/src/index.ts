/**
 * @afri/oracle — TypeScript SDK for the AFRI Africa Oracle.
 *
 * Works in browsers, Node ≥18, Deno, Bun, Cloudflare Workers — anywhere
 * with a global `fetch`. No deps.
 */

export const DEFAULT_BASE_URL =
  (typeof process !== "undefined" && process.env?.AFRICA_ORACLE_URL) ||
  "https://africa-oracle.fly.dev";

export const DEFAULT_TIMEOUT_MS = 10_000;

export class OracleError extends Error {
  constructor(message: string, public readonly status?: number) {
    super(message);
    this.name = "OracleError";
  }
}

export interface PriceFeed {
  provider: string;
  provider_slug: string;
  country: string;
  currency: string;
  buy_price: number;
  sell_price: number;
  mid_price: number;
  spread: number;
  spread_bps: number;
  volume_24h: number;
  confidence: number;
  timestamp: number;
  agent_id: string;
  simulated: boolean;
}

export interface QuorumReport {
  oracle_id: string;
  timestamp: number;
  currencies: number;
  prices: Array<Record<string, unknown>>;
  quorum_failed: Array<{ currency: string; distinct_providers: number }>;
}

export interface ClientOptions {
  baseUrl?: string;
  timeoutMs?: number;
  fetch?: typeof fetch;
}

export class Client {
  private readonly baseUrl: string;
  private readonly timeoutMs: number;
  private readonly _fetch: typeof fetch;

  constructor(opts: ClientOptions = {}) {
    this.baseUrl = (opts.baseUrl ?? DEFAULT_BASE_URL).replace(/\/$/, "");
    this.timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    this._fetch = opts.fetch ?? fetch;
    if (!this._fetch) {
      throw new OracleError("no fetch available — pass opts.fetch on Node <18");
    }
  }

  private async request<T>(path: string, body?: unknown): Promise<T> {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), this.timeoutMs);
    try {
      const res = await this._fetch(`${this.baseUrl}${path}`, {
        method: body === undefined ? "GET" : "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: ctrl.signal,
      });
      if (!res.ok) {
        throw new OracleError(`${res.status} ${res.statusText} @ ${path}`, res.status);
      }
      return (await res.json()) as T;
    } catch (e) {
      if (e instanceof OracleError) throw e;
      throw new OracleError(`network: ${(e as Error).message} @ ${path}`);
    } finally {
      clearTimeout(t);
    }
  }

  health(): Promise<{ status: string; version: string; providers: number; uptime_s: number }> {
    return this.request("/health");
  }

  providers(): Promise<Record<string, { name: string; countries: string[]; agent_count: number }>> {
    return this.request("/providers");
  }

  hunt(provider: string, country: string, simulate = true): Promise<PriceFeed> {
    return this.request<PriceFeed>("/hunt", { provider, country, simulate });
  }

  feedsAll(): Promise<QuorumReport> {
    return this.request<QuorumReport>("/feeds/all", {});
  }

  feedsQuorum(minProviders = 2): Promise<QuorumReport> {
    return this.request<QuorumReport>("/feeds/quorum", { min_providers: minProviders });
  }

  /** Subscribe to /feeds/stream (SSE). Returns a stop() function. */
  streamFeeds(
    onData: (report: QuorumReport) => void,
    opts: { intervalSec?: number; onError?: (e: Error) => void } = {},
  ): () => void {
    const interval = opts.intervalSec ?? 30;
    const url = `${this.baseUrl}/feeds/stream?interval=${interval}`;
    if (typeof EventSource === "undefined") {
      throw new OracleError("EventSource not available — use feedsQuorum() polling on Node");
    }
    const es = new EventSource(url);
    es.onmessage = (ev) => {
      try {
        onData(JSON.parse(ev.data));
      } catch (e) {
        opts.onError?.(e as Error);
      }
    };
    es.onerror = () => opts.onError?.(new OracleError("stream error"));
    return () => es.close();
  }
}

export default Client;
