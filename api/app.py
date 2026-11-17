"""FastAPI ASGI wrapper around oracle_agent.py.

Endpoints:
  GET  /                — dashboard UI (single-page, self-contained)
  GET  /health          — liveness + version + provider count
  GET  /providers       — provider/country/currency map
  GET  /rates           — compact rate map; ?from=&to=&amount= adds a conversion
  POST /hunt            — single feed: {provider, country, simulate}
  POST /feeds/all       — aggregated feed (median + vol-weighted spread)
  POST /feeds/quorum    — resilient feed: only currencies with ≥ min_providers
  POST /feeds/robust    — quorum + Tukey-fence outlier filter
  POST /feeds/evolved   — robust + fitness-weighted consensus (EvoOracle flywheel)
  POST /convert         — cross-currency conversion (from, to, amount, side)
  GET  /evo/genome      — provider-fitness genome + trajectory count
  GET  /feeds/stream    — Server-Sent Events: aggregate every interval seconds
  GET  /metrics         — Prometheus text format: oracle counters
  GET  /                      — dashboard UI (single-page, self-contained)
  GET  /health                — liveness + version + provider count
  GET  /providers             — provider/country/currency map
  POST /hunt                  — single feed: {provider, country, simulate}
  POST /feeds/all             — aggregated feed (median + vol-weighted spread)
  POST /feeds/quorum          — resilient feed: ≥ min_providers
  POST /feeds/robust          — quorum + Tukey-fence outlier filter
  POST /convert               — cross-currency conversion (from, to, amount, side)
  GET  /rate/{from}/{to}      — simple GET rate (cacheable, cite-friendly)
  GET  /widget.js             — embeddable live-rate widget (one-line integration)
  GET  /feeds/stream          — Server-Sent Events
  GET  /metrics               — Prometheus text format
  GET  /llms.txt              — AI-crawler guide
  GET  /ai.txt                — AI agent policy
  GET  /.well-known/*         — ai-plugin.json, security.txt
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    HTMLResponse, JSONResponse, PlainTextResponse, Response, StreamingResponse,
)
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evo_oracle import EvoOracle, evolved_robust_aggregate  # noqa: E402
from oracle_agent import PROVIDERS, OracleAgent, OracleAggregator, convert_amount  # noqa: E402

VERSION = "0.7.0"
CACHE_TTL_S = 10
RATE_LIMIT_PER_MIN = 60
RATE_BUCKETS_MAX = 4096
DASHBOARD_PATH = Path(__file__).resolve().parent / "static" / "index.html"
VERSION = "0.9.0"
CACHE_TTL_S = 10
RATE_LIMIT_PER_MIN = 60
REPO_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"
DASHBOARD_PATH = STATIC_DIR / "index.html"

_evo = EvoOracle(os.environ.get("ORACLE_EVO_DIR", "evo-data"))

app = FastAPI(
    title="Africa Oracle Extraction Agent",
    version=VERSION,
    description="Resilient, sovereign, scalable mobile-money price oracle for African stablecoins.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    max_age=600,
)


# ─── Request models ──────────────────────────────────────────────────────────
class HuntRequest(BaseModel):
    provider: str = Field(..., description="safaricom | airtel | orange | mtn")
    country: str = Field(..., description="ISO 3166-1 alpha-2, e.g. KE, NG")
    simulate: bool = Field(default=True)


class QuorumRequest(BaseModel):
    min_providers: int = Field(default=2, ge=1, le=4)


class RobustRequest(BaseModel):
    min_providers: int = Field(default=2, ge=1, le=4)
    tukey_k: float = Field(default=1.5, ge=0.5, le=3.0)


class ConvertRequest(BaseModel):
    from_currency: str = Field(..., alias="from", min_length=3, max_length=3)
    to_currency: str = Field(..., alias="to", min_length=3, max_length=3)
    amount: float = Field(..., gt=0)
    side: str = Field(default="mid", pattern="^(mid|buy|sell)$")

    model_config = {"populate_by_name": True}


# ─── Metrics ─────────────────────────────────────────────────────────────────
_metrics: dict[str, int] = {
    "hunt_requests_total": 0,
    "hunt_errors_total": 0,
    "feeds_all_requests_total": 0,
    "feeds_quorum_requests_total": 0,
    "feeds_robust_requests_total": 0,
    "feeds_stream_connections_total": 0,
    "feeds_quorum_failed_total": 0,
    "feeds_outliers_dropped_total": 0,
    "convert_requests_total": 0,
    "rates_requests_total": 0,
    "feeds_evolved_requests_total": 0,
    "rate_requests_total": 0,
    "widget_requests_total": 0,
    "seo_requests_total": 0,
    "cache_hits_total": 0,
    "cache_misses_total": 0,
    "rate_limited_total": 0,
    "mcp_requests_total": 0,
    "history_requests_total": 0,
    "snapshot_requests_total": 0,
    "snapshot_hits_total": 0,
    "snapshot_misses_total": 0,
}


# ─── Latency reservoir (tiny, lock-free, p50/p95 only on /metrics) ──────────
# Keep last N latencies per key — compact and dependency-free (no numpy).
_LATENCY_CAP = 256
_latencies: dict[str, deque] = defaultdict(lambda: deque(maxlen=_LATENCY_CAP))


def _record_latency(key: str, seconds: float) -> None:
    _latencies[key].append(seconds)


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    i = int(q * (len(s) - 1))
    return s[i]


# ─── TTL cache (simple, in-process) ──────────────────────────────────────────
_cache: dict[str, tuple[float, dict]] = {}

# ─── History ring buffer (60 min @ 30s cadence = 120 entries) + snapshot index
HISTORY_WINDOW_S = 3600
HISTORY_CAP = 120
_history: deque = deque(maxlen=HISTORY_CAP)        # list[dict] — compact snapshots
_snapshots: dict[str, dict] = {}                   # oracle_id → full feed (frozen)
SNAPSHOT_CAP = 240                                 # keep ~2× history, drop oldest


def _record_snapshot(feed: dict) -> None:
    """Called on each fresh robust-aggregator snapshot. Captures a compact
    time-series entry for /history plus a frozen full feed for /snapshot."""
    oracle_id = feed.get("oracle_id")
    ts = feed.get("timestamp")
    if not oracle_id or not ts:
        return
    compact = {
        "oracle_id": oracle_id,
        "timestamp": ts,
        "mid": {p["currency"]: p["mid_price"] for p in feed.get("prices", [])},
    }
    _history.append(compact)
    _snapshots[oracle_id] = feed
    if len(_snapshots) > SNAPSHOT_CAP:
        # Drop oldest by iteration order (dict preserves insertion order)
        oldest = next(iter(_snapshots))
        _snapshots.pop(oldest, None)


async def _cached(key: str, fn) -> dict:
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < CACHE_TTL_S:
        _metrics["cache_hits_total"] += 1
        value = hit[1]
        # Keep snapshot index alive for cache-hit traffic too — dict re-set
        # is idempotent, so no duplicate history entry, and /snapshot stays
        # retrievable as long as the cached feed is warm.
        if key.startswith("robust:") and "prices" in value:
            oid = value.get("oracle_id")
            if oid and oid not in _snapshots:
                _snapshots[oid] = value
        return value
    _metrics["cache_misses_total"] += 1
    t0 = time.monotonic()
    value = await asyncio.to_thread(fn)
    _record_latency(key, time.monotonic() - t0)
    _cache[key] = (now, value)
    # Record robust snapshots for /history + /snapshot (that's the feed with
    # the broadest currency coverage and the most anti-manipulation defence).
    if key.startswith("robust:") and "prices" in value:
        _record_snapshot(value)
    return value


# ─── Rate limiting (per-IP token-bucket, in-process) ─────────────────────────
_rate_buckets: dict[str, deque] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    # Behind Fly/Vercel the socket peer is the edge proxy — without this every
    # user would share one bucket. Headers are proxy-set, not client-set, on
    # those platforms.
    fly = request.headers.get("fly-client-ip")
    if fly:
        return fly
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "?"


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    path = request.url.path
    if (path in ("/health", "/metrics", "/", "/llms.txt", "/ai.txt", "/widget.js",
                 "/robots.txt", "/sitemap.xml", "/feed.xml", "/faq", "/mcp.json",
                 "/changelog")
            or path.startswith("/static")
            or path.startswith("/.well-known/")
            or path.startswith("/openapi")
            or path.startswith("/docs")
            or path.startswith("/redoc")):
        return await call_next(request)
    ip = _client_ip(request)
    bucket = _rate_buckets[ip]
    now = time.time()
    while bucket and now - bucket[0] > 60:
        bucket.popleft()
    if len(bucket) >= RATE_LIMIT_PER_MIN:
        _metrics["rate_limited_total"] += 1
        return JSONResponse(
            status_code=429,
            content={"error": "rate limit exceeded", "retry_after_s": 60},
            headers={"Retry-After": "60"},
        )
    bucket.append(now)
    if len(_rate_buckets) > RATE_BUCKETS_MAX:
        for stale_ip in [k for k, b in _rate_buckets.items() if not b or now - b[-1] > 60]:
            del _rate_buckets[stale_ip]
    return await call_next(request)


# ─── Aggregator factory ──────────────────────────────────────────────────────
def _build_aggregator() -> OracleAggregator:
    agg = OracleAggregator()
    for slug, info in PROVIDERS.items():
        for country in info["countries"]:
            try:
                agg.add_agent(OracleAgent(slug, country, simulate=True))
            except ValueError:
                continue
    return agg


# ─── Routes ──────────────────────────────────────────────────────────────────
try:
    _dashboard_html = DASHBOARD_PATH.read_text(encoding="utf-8")
except OSError:
    _dashboard_html = (
@app.get("/", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    if DASHBOARD_PATH.exists():
        html = DASHBOARD_PATH.read_text(encoding="utf-8").replace("{{VERSION}}", VERSION)
        return HTMLResponse(html)
    return HTMLResponse(
        f"<h1>Africa Oracle {VERSION}</h1><p>API is running. See <a href='/docs'>/docs</a>.</p>"
    )


@app.get("/", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    return HTMLResponse(_dashboard_html)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": VERSION,
        "providers": len(PROVIDERS),
        "uptime_s": int(time.time() - _started),
    }


@app.get("/providers")
def list_providers() -> dict:
    return {
        slug: {
            "name": info["name"],
            "countries": info["countries"],
            "agent_count": info["agent_count"],
        }
        for slug, info in PROVIDERS.items()
    }


@app.post("/hunt")
def hunt(req: HuntRequest) -> dict:
    _metrics["hunt_requests_total"] += 1
    try:
        agent = OracleAgent(req.provider, req.country, simulate=req.simulate)
    except ValueError as e:
        _metrics["hunt_errors_total"] += 1
        raise HTTPException(status_code=400, detail=str(e))
    try:
        return agent.fetch_price()
    except NotImplementedError as e:
        _metrics["hunt_errors_total"] += 1
        raise HTTPException(status_code=501, detail=str(e))


@app.post("/feeds/all")
async def feeds_all() -> dict:
    _metrics["feeds_all_requests_total"] += 1
    return await _cached("all", lambda: _build_aggregator().aggregate())


@app.post("/feeds/quorum")
async def feeds_quorum(req: QuorumRequest) -> dict:
    _metrics["feeds_quorum_requests_total"] += 1
    result = await _cached(
        f"quorum:{req.min_providers}",
        lambda: _build_aggregator().quorum_aggregate(req.min_providers),
    )
    _metrics["feeds_quorum_failed_total"] += len(result.get("quorum_failed", []))
    return result


@app.post("/feeds/robust")
async def feeds_robust(req: RobustRequest) -> dict:
    """Resilient — quorum + Tukey-fence outlier filter on mid_price."""
    _metrics["feeds_robust_requests_total"] += 1
    # Quantize tukey_k so the cache key space stays bounded (a continuous
    # float would let clients mint unlimited cache entries).
    k = round(req.tukey_k, 1)
    result = await _cached(
        f"robust:{req.min_providers}:{k}",
        lambda: _build_aggregator().robust_quorum_aggregate(req.min_providers, k),
    )
    _metrics["feeds_quorum_failed_total"] += len(result.get("quorum_failed", []))
    _metrics["feeds_outliers_dropped_total"] += len(result.get("outliers_dropped", []))
    return result


@app.post("/feeds/evolved")
async def feeds_evolved(req: RobustRequest) -> dict:
    """EvoOracle flywheel — robust filter, trajectory capture, then
    fitness-weighted consensus. Every call sharpens the genome."""
    _metrics["feeds_evolved_requests_total"] += 1
    k = round(req.tukey_k, 1)
    return await _cached(
        f"evolved:{req.min_providers}:{k}",
        lambda: evolved_robust_aggregate(_build_aggregator(), _evo, req.min_providers, k),
    )


@app.get("/evo/genome")
def evo_genome() -> dict:
    """The moat, inspectable: per-source fitness + accumulated trajectories."""
    return _evo.stats()


@app.get("/rates")
async def rates(
    from_ccy: str | None = Query(default=None, alias="from", min_length=3, max_length=3),
    to_ccy: str | None = Query(default=None, alias="to", min_length=3, max_length=3),
    amount: float | None = Query(default=None, gt=0),
) -> dict:
    """One-GET integration surface: compact rate map, optionally a conversion.

        curl https://<host>/rates
        curl "https://<host>/rates?from=KES&to=NGN&amount=1000"
    """
    _metrics["rates_requests_total"] += 1
    feed = await _cached(
        "robust:1:1.5",
        lambda: _build_aggregator().robust_quorum_aggregate(1, 1.5),
    )
    out = {
        "base": "USD",
        "timestamp": feed.get("timestamp"),
        "rates": {
            p["currency"]: {
                "mid": p["mid_price"], "buy": p["buy_price"],
                "sell": p["sell_price"], "confidence": p["avg_confidence"],
            }
            for p in feed.get("prices", [])
        },
    }
    if from_ccy and to_ccy and amount:
        try:
            out["conversion"] = convert_amount(
                feed, from_ccy.upper(), to_ccy.upper(), amount, "mid"
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    return out


@app.post("/convert")
async def convert(req: ConvertRequest) -> dict:
    """Cross-currency conversion using the robust aggregated feed.

    Powers remittance, merchant, and traveler flows — the killer use case.
    """
    _metrics["convert_requests_total"] += 1
    # Broaden coverage for the converter (min_providers=1) while keeping the
    # Tukey outlier filter — otherwise single-provider currencies (e.g. NGN)
    # would be invisible to consumers.
    feed = await _cached(
        "robust:1:1.5",
        lambda: _build_aggregator().robust_quorum_aggregate(1, 1.5),
    )
    try:
        return convert_amount(
            feed,
            req.from_currency.upper(),
            req.to_currency.upper(),
            req.amount,
            req.side,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


async def _sse_loop(interval: int) -> AsyncGenerator[bytes, None]:
    _metrics["feeds_stream_connections_total"] += 1
    while True:
        data = await _cached("all", lambda: _build_aggregator().aggregate())
        payload = json.dumps(
            {
                "oracle_id": data.get("oracle_id"),
                "timestamp": data.get("timestamp"),
                "currencies": data.get("currencies"),
                "prices": data.get("prices"),
            },
            default=str,
        )
        yield f"data: {payload}\n\n".encode()
        await asyncio.sleep(interval)


@app.get("/feeds/stream")
async def feeds_stream(interval: int = Query(default=30, ge=5, le=300)) -> StreamingResponse:
    """SSE — affordable scale path (no per-poll HTTP overhead)."""
    return StreamingResponse(_sse_loop(interval), media_type="text/event-stream")


# ─── Cite-friendly GET rate (for docs, chatbots, AI search agents) ───────────
@app.get("/rate/{from_ccy}/{to_ccy}")
async def rate(from_ccy: str, to_ccy: str) -> dict:
    """Simple GET exchange rate. Cacheable, bookmarkable, cite-friendly."""
    _metrics["rate_requests_total"] += 1
    feed = await _cached(
        "robust:1:1.5",
        lambda: _build_aggregator().robust_quorum_aggregate(1, 1.5),
    )
    try:
        out = convert_amount(feed, from_ccy.upper(), to_ccy.upper(), 1.0, "mid")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {
        "from": from_ccy.upper(),
        "to": to_ccy.upper(),
        "rate": out["rate"],
        "confidence": out["confidence"],
        "spread_bps": out["spread_bps"],
        "timestamp": feed.get("timestamp"),
        "providers": sorted(set(out["providers_from"] + out["providers_to"])),
    }


# ─── Embeddable widget (commercial distribution lever) ───────────────────────
_WIDGET_PATH = STATIC_DIR / "widget.js"


@app.get("/widget.js")
def widget_js() -> Response:
    """Embeddable widget. Usage:
        <script src="https://africa-oracle.fly.dev/widget.js"
                data-from="USD" data-to="KES" data-amount="100"></script>
    """
    _metrics["widget_requests_total"] += 1
    return Response(
        _WIDGET_PATH.read_text(encoding="utf-8"),
        media_type="application/javascript",
        headers={"Cache-Control": "public, max-age=300"},
    )


# ─── AI-discoverability (GEO: llms.txt, ai.txt, .well-known) ─────────────────
def _serve_file(path: Path, media: str, cache_s: int = 3600) -> Response:
    if not path.exists():
        raise HTTPException(status_code=404)
    return Response(
        path.read_bytes(),
        media_type=media,
        headers={"Cache-Control": f"public, max-age={cache_s}"},
    )


@app.get("/llms.txt", response_class=PlainTextResponse)
def llms_txt() -> Response:
    """Guide for LLM crawlers (ChatGPT Search, Claude, Perplexity, etc.)."""
    return _serve_file(REPO_ROOT / "llms.txt", "text/plain; charset=utf-8")


@app.get("/ai.txt", response_class=PlainTextResponse)
def ai_txt() -> Response:
    """AI-agent policy (training data, attribution, rate limits)."""
    return _serve_file(REPO_ROOT / "ai.txt", "text/plain; charset=utf-8")


@app.get("/.well-known/ai-plugin.json")
def ai_plugin() -> Response:
    """OpenAI-style plugin manifest for ChatGPT / Claude / similar."""
    return _serve_file(REPO_ROOT / ".well-known" / "ai-plugin.json", "application/json")


@app.get("/.well-known/security.txt", response_class=PlainTextResponse)
def security_txt() -> Response:
    """RFC 9116 security contact."""
    return _serve_file(REPO_ROOT / ".well-known" / "security.txt", "text/plain; charset=utf-8")


# ─── Classic + agentic SEO surfaces ──────────────────────────────────────────

_PUBLIC_ORIGIN = "https://africa-oracle.fly.dev"
_PUBLIC_PATHS = [
    ("/", "daily", "1.0"),
    ("/faq", "weekly", "0.9"),
    ("/docs", "weekly", "0.8"),
    ("/redoc", "weekly", "0.7"),
    ("/providers", "weekly", "0.6"),
    ("/health", "always", "0.3"),
]


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots_txt() -> Response:
    """Classic robots.txt — explicit allows for AI bots + sitemap pointer."""
    _metrics["seo_requests_total"] += 1
    lines = [
        "User-agent: *",
        "Allow: /",
        "",
    ]
    for bot in ("GPTBot", "ClaudeBot", "anthropic-ai", "Google-Extended",
                "PerplexityBot", "CCBot", "OAI-SearchBot", "Applebot-Extended"):
        lines.append(f"User-agent: {bot}")
        lines.append("Allow: /")
        lines.append("")
    lines.append(f"Sitemap: {_PUBLIC_ORIGIN}/sitemap.xml")
    lines.append(f"Sitemap: {_PUBLIC_ORIGIN}/llms.txt")
    return Response("\n".join(lines) + "\n", media_type="text/plain; charset=utf-8")


@app.get("/sitemap.xml")
def sitemap_xml() -> Response:
    """XML sitemap — the classic surface still read by every indexer."""
    _metrics["seo_requests_total"] += 1
    today = datetime.utcnow().strftime("%Y-%m-%d")
    urls = "\n".join(
        f'  <url><loc>{_PUBLIC_ORIGIN}{path}</loc>'
        f'<lastmod>{today}</lastmod>'
        f'<changefreq>{freq}</changefreq>'
        f'<priority>{pri}</priority></url>'
        for path, freq, pri in _PUBLIC_PATHS
    )
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f'{urls}\n</urlset>\n'
    )
    return Response(body, media_type="application/xml")


@app.get("/feed.xml")
async def feed_xml() -> Response:
    """RSS 2.0 of the current robust feed. Every price update since
    the cache rolled is one <item>. Consumed by RSS readers, Zapier,
    Make.com, IFTTT, and every LLM that still indexes feeds."""
    _metrics["seo_requests_total"] += 1
    data = await _cached(
        "robust:1:1.5",
        lambda: _build_aggregator().robust_quorum_aggregate(1, 1.5),
    )
    oracle_id = data.get("oracle_id", "feed")
    ts = data.get("timestamp", int(time.time()))
    build_date = datetime.utcfromtimestamp(ts).strftime("%a, %d %b %Y %H:%M:%S GMT")
    items = []
    for p in data.get("prices", []):
        ccy = p["currency"]
        title = f"{ccy} · 1 USD = {p['mid_price']} {ccy}"
        desc = (f"Median price across {p['agent_count']} agents · "
                f"{', '.join(p['providers'])} · "
                f"spread {p['spread_bps']}bps · "
                f"confidence {p['avg_confidence']*100:.1f}%")
        guid = f"{oracle_id}:{ccy}:{ts}"
        items.append(
            f"<item>"
            f"<title>{title}</title>"
            f"<link>{_PUBLIC_ORIGIN}/rate/USD/{ccy}</link>"
            f"<guid isPermaLink=\"false\">{guid}</guid>"
            f"<pubDate>{build_date}</pubDate>"
            f"<description>{desc}</description>"
            f"</item>"
        )
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        '<channel>\n'
        '  <title>Africa Oracle · Live Rates</title>\n'
        f'  <link>{_PUBLIC_ORIGIN}/</link>\n'
        f'  <atom:link href="{_PUBLIC_ORIGIN}/feed.xml" rel="self" type="application/rss+xml" />\n'
        '  <description>Live median FX rates for African currencies — '
        'M-Pesa, Airtel, Orange, MTN. Updated every 10 seconds.</description>\n'
        '  <language>en</language>\n'
        f'  <lastBuildDate>{build_date}</lastBuildDate>\n'
        f'  <ttl>1</ttl>\n'
        + "\n  ".join(items)
        + '\n</channel>\n</rss>\n'
    )
    return Response(body, media_type="application/rss+xml")


# ─── /.well-known/agents.json — emerging agent-discovery manifest ────────────
@app.get("/.well-known/agents.json")
def agents_json() -> dict:
    """Agent-to-agent discovery (A2A / AGNTCY lineage). Lets other AI
    agents discover this oracle's capabilities as a first-class peer."""
    _metrics["seo_requests_total"] += 1
    return {
        "schema_version": "0.1",
        "name": "africa-oracle",
        "display_name": "Africa Oracle",
        "description": "Resilient mobile-money price oracle for African currencies.",
        "version": VERSION,
        "vendor": {
            "name": "Africa Oracle contributors",
            "url": "https://github.com/nzengou/africa-oracle-agent",
        },
        "endpoints": {
            "base_url": _PUBLIC_ORIGIN,
            "openapi": f"{_PUBLIC_ORIGIN}/openapi.json",
            "mcp": f"{_PUBLIC_ORIGIN}/mcp.json",
            "sse": f"{_PUBLIC_ORIGIN}/feeds/stream",
        },
        "capabilities": [
            "currency.convert",
            "currency.rate",
            "currency.list",
            "feed.aggregate",
            "feed.stream",
        ],
        "authentication": {"type": "none", "rate_limit_per_minute": RATE_LIMIT_PER_MIN},
        "facts_url": "https://github.com/nzengou/africa-oracle-agent/blob/main/FACTS.md",
        "license": "https://github.com/nzengou/africa-oracle-agent/blob/main/LICENSE",
    }


# ─── /mcp.json — Model Context Protocol tool descriptor ──────────────────────
@app.get("/mcp.json")
def mcp_json() -> dict:
    """MCP tool descriptor — lets Claude Desktop, Cursor, and other
    MCP-aware agents wire the oracle in as native tools."""
    _metrics["seo_requests_total"] += 1
    return {
        "schema_version": "mcp-tools/0.1",
        "server": {
            "name": "africa-oracle",
            "version": VERSION,
            "description": "Live mobile-money FX for African currencies.",
            "transport": "http",
            "base_url": _PUBLIC_ORIGIN,
        },
        "tools": [
            {
                "name": "convert_currency",
                "description": "Convert an amount between two currencies using the quorum-protected oracle feed. USD is supported as the base currency.",
                "method": "POST",
                "path": "/convert",
                "input_schema": {
                    "type": "object",
                    "required": ["from", "to", "amount"],
                    "properties": {
                        "from": {"type": "string", "description": "ISO 4217 source currency (USD, KES, NGN, ...)"},
                        "to": {"type": "string", "description": "ISO 4217 target currency"},
                        "amount": {"type": "number", "minimum": 0},
                        "side": {"type": "string", "enum": ["mid", "buy", "sell"], "default": "mid"},
                    },
                },
            },
            {
                "name": "get_rate",
                "description": "Get the current exchange rate between two currencies.",
                "method": "GET",
                "path_template": "/rate/{from}/{to}",
            },
            {
                "name": "list_providers",
                "description": "List configured mobile-money providers and the countries/currencies they cover.",
                "method": "GET",
                "path": "/providers",
            },
            {
                "name": "robust_feed",
                "description": "Full aggregated feed with Tukey-fence outlier filter and quorum protection.",
                "method": "POST",
                "path": "/feeds/robust",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "min_providers": {"type": "integer", "minimum": 1, "maximum": 4, "default": 2},
                        "tukey_k": {"type": "number", "minimum": 0.5, "maximum": 3.0, "default": 1.5},
                    },
                },
            },
        ],
    }


# ─── /faq — human + machine-readable FAQ (FAQPage JSON-LD) ───────────────────
_FAQ_PATH = STATIC_DIR / "faq.json"


def _load_faq() -> list[tuple[str, str]]:
    return [(q, a) for q, a in json.loads(_FAQ_PATH.read_text(encoding="utf-8"))]


@app.get("/faq", response_class=HTMLResponse)
def faq() -> HTMLResponse:
    """FAQ page with FAQPage JSON-LD — big LLM citation surface."""
    _metrics["seo_requests_total"] += 1
    faq_items = _load_faq()
    qa_rows = "".join(
        f'<details><summary>{q}</summary><p>{a}</p></details>'
        for q, a in faq_items
    )
    jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q,
             "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in faq_items
        ],
    })
    html = (
        '<!doctype html><html lang="en"><head>'
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Africa Oracle · FAQ</title>'
        '<meta name="description" content="Frequently asked questions about Africa Oracle: a resilient mobile-money FX price oracle for African currencies.">'
        '<link rel="canonical" href="https://africa-oracle.fly.dev/faq">'
        '<meta property="og:title" content="Africa Oracle · FAQ">'
        '<meta name="robots" content="index,follow,max-snippet:-1">'
        f'<script type="application/ld+json">{jsonld}</script>'
        '<style>'
        ':root{--bg:#f6f8fb;--fg:#0b1220;--muted:#5c6473;--card:#fff;--border:#e5e9f0;--accent:#d97706}'
        '@media(prefers-color-scheme:dark){:root{--bg:#0b1220;--fg:#e6ebf5;--muted:#8b93a7;--card:#131b2e;--border:#1f2a44;--accent:#f59e0b}}'
        'body{margin:0;padding:40px 20px;font:16px/1.6 -apple-system,BlinkMacSystemFont,system-ui,sans-serif;background:var(--bg);color:var(--fg);max-width:720px;margin-inline:auto}'
        'h1{margin:0 0 8px;font-size:22px}'
        'p.lede{color:var(--muted);margin:0 0 24px}'
        'details{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px 16px;margin:8px 0}'
        'summary{font-weight:600;cursor:pointer}'
        'details[open] summary{margin-bottom:8px}'
        'details p{margin:0;color:var(--muted)}'
        'nav{margin-top:40px;padding-top:20px;border-top:1px solid var(--border);font-size:13px;color:var(--muted)}'
        'nav a{color:var(--accent);text-decoration:none}'
        '</style></head><body>'
        '<h1>Africa Oracle · FAQ</h1>'
        '<p class="lede">Every answer below maps to a file or function in the <a href="https://github.com/nzengou/africa-oracle-agent">source repository</a>. See <a href="https://github.com/nzengou/africa-oracle-agent/blob/main/FACTS.md">FACTS.md</a> for the full ledger.</p>'
        f'{qa_rows}'
        '<nav>'
        '<a href="/">dashboard</a> · '
        '<a href="/docs">API docs</a> · '
        '<a href="/changelog">changelog</a> · '
        '<a href="/llms.txt">llms.txt</a> · '
        '<a href="/mcp.json">mcp.json</a> · '
        '<a href="/.well-known/agents.json">agents.json</a>'
        '</nav></body></html>'
    )
    return HTMLResponse(html)


@app.get("/metrics", response_class=PlainTextResponse)
def metrics() -> str:
    lines = [
        "# HELP africa_oracle_info Africa Oracle build info",
        "# TYPE africa_oracle_info gauge",
        f'africa_oracle_info{{version="{VERSION}"}} 1',
        "# HELP africa_oracle_providers_total Configured providers",
        "# TYPE africa_oracle_providers_total gauge",
        f"africa_oracle_providers_total {len(PROVIDERS)}",
        "# HELP africa_oracle_history_size Entries in the history ring buffer",
        "# TYPE africa_oracle_history_size gauge",
        f"africa_oracle_history_size {len(_history)}",
        "# HELP africa_oracle_snapshot_index_size Distinct oracle_ids retained",
        "# TYPE africa_oracle_snapshot_index_size gauge",
        f"africa_oracle_snapshot_index_size {len(_snapshots)}",
    ]
    for key, val in _metrics.items():
        lines.append(f"# TYPE africa_oracle_{key} counter")
        lines.append(f"africa_oracle_{key} {val}")
    # p50 / p95 latency on cached aggregator computation paths
    for key, samples in _latencies.items():
        if not samples:
            continue
        safe = key.replace(":", "_").replace(".", "_")
        values = list(samples)
        lines.append(f"# TYPE africa_oracle_aggregator_p50_seconds gauge")
        lines.append(f'africa_oracle_aggregator_p50_seconds{{op="{safe}"}} {_quantile(values, 0.5):.6f}')
        lines.append(f"# TYPE africa_oracle_aggregator_p95_seconds gauge")
        lines.append(f'africa_oracle_aggregator_p95_seconds{{op="{safe}"}} {_quantile(values, 0.95):.6f}')
    return "\n".join(lines) + "\n"


# ─── History (in-memory time series) ─────────────────────────────────────────
@app.get("/history/{from_ccy}/{to_ccy}")
async def history(from_ccy: str, to_ccy: str,
                  since: int = Query(default=1800, ge=60, le=HISTORY_WINDOW_S),
                  limit: int = Query(default=120, ge=1, le=HISTORY_CAP)) -> dict:
    """Time series of mid-price rate (`from_ccy` -> `to_ccy`) from the ring
    buffer. `since` is seconds back from now. USD leg is always 1.0."""
    _metrics["history_requests_total"] += 1
    frm, to = from_ccy.upper(), to_ccy.upper()
    # Ensure we have *some* history to serve — warm the ring if empty
    if not _history:
        await _cached(
            "robust:1:1.5",
            lambda: _build_aggregator().robust_quorum_aggregate(1, 1.5),
        )
    now = int(time.time())
    cutoff = now - since
    series = []
    for entry in list(_history)[-limit:]:
        if entry["timestamp"] < cutoff:
            continue
        mids = dict(entry["mid"])
        mids.setdefault("USD", 1.0)  # synthetic USD base (parity with /convert)
        src, dst = mids.get(frm), mids.get(to)
        if src is None or dst is None:
            continue
        series.append({"t": entry["timestamp"], "rate": round(dst / src, 6),
                       "oracle_id": entry["oracle_id"]})
    return {
        "from": frm, "to": to,
        "since_s": since, "points": len(series),
        "series": series,
    }


# ─── /snapshot/{oracle_id} — content-addressable frozen feed ─────────────────
@app.get("/snapshot/{oracle_id}")
def snapshot(oracle_id: str) -> dict:
    """Return the exact frozen robust-feed for an oracle_id. Lets AI agents
    cite a specific moment and lets independent parties verify a claim after
    the fact. 404 if the snapshot aged out of the ring (approximately 2 hours)."""
    _metrics["snapshot_requests_total"] += 1
    snap = _snapshots.get(oracle_id)
    if snap is None:
        _metrics["snapshot_misses_total"] += 1
        raise HTTPException(status_code=404, detail=f"snapshot aged out or unknown: {oracle_id}")
    _metrics["snapshot_hits_total"] += 1
    return snap


# ─── POST /mcp — real MCP streamable-http server (JSON-RPC 2.0) ──────────────
_MCP_PROTOCOL_VERSION = "2024-11-05"
_MCP_TOOLS = [
    {
        "name": "convert_currency",
        "description": "Convert an amount between two currencies using the quorum-protected oracle feed. USD is supported as the base currency.",
        "inputSchema": {
            "type": "object",
            "required": ["from_currency", "to_currency", "amount"],
            "properties": {
                "from_currency": {"type": "string", "description": "ISO 4217 source currency (USD, KES, NGN, ...)"},
                "to_currency": {"type": "string", "description": "ISO 4217 target currency"},
                "amount": {"type": "number", "minimum": 0},
                "side": {"type": "string", "enum": ["mid", "buy", "sell"], "default": "mid"},
            },
        },
    },
    {
        "name": "get_rate",
        "description": "Get the current exchange rate between two currencies.",
        "inputSchema": {
            "type": "object",
            "required": ["from_currency", "to_currency"],
            "properties": {
                "from_currency": {"type": "string"},
                "to_currency": {"type": "string"},
            },
        },
    },
    {
        "name": "list_providers",
        "description": "List configured mobile-money providers and the countries/currencies they cover.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "robust_feed",
        "description": "Full aggregated feed with Tukey-fence outlier filter and quorum protection.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "min_providers": {"type": "integer", "minimum": 1, "maximum": 4, "default": 2},
                "tukey_k": {"type": "number", "minimum": 0.5, "maximum": 3.0, "default": 1.5},
            },
        },
    },
]


def _mcp_error(req_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _mcp_text_result(req_id, payload: dict | str) -> dict:
    text = payload if isinstance(payload, str) else json.dumps(payload, default=str)
    return {
        "jsonrpc": "2.0", "id": req_id,
        "result": {"content": [{"type": "text", "text": text}], "isError": False},
    }


async def _mcp_call_tool(name: str, args: dict) -> dict:
    """Invoke a single MCP tool and return a dict ready to put in result.content.
    Wraps the existing HTTP handlers so the two surfaces stay in lockstep."""
    if name == "convert_currency":
        feed = await _cached(
            "robust:1:1.5",
            lambda: _build_aggregator().robust_quorum_aggregate(1, 1.5),
        )
        return convert_amount(
            feed,
            str(args["from_currency"]).upper(),
            str(args["to_currency"]).upper(),
            float(args["amount"]),
            str(args.get("side", "mid")),
        )
    if name == "get_rate":
        feed = await _cached(
            "robust:1:1.5",
            lambda: _build_aggregator().robust_quorum_aggregate(1, 1.5),
        )
        c = convert_amount(
            feed,
            str(args["from_currency"]).upper(),
            str(args["to_currency"]).upper(),
            1.0, "mid",
        )
        return {
            "from": c["from"]["currency"], "to": c["to"]["currency"],
            "rate": c["rate"], "confidence": c["confidence"],
            "spread_bps": c["spread_bps"], "timestamp": feed.get("timestamp"),
        }
    if name == "list_providers":
        return {slug: {"name": info["name"], "countries": info["countries"]}
                for slug, info in PROVIDERS.items()}
    if name == "robust_feed":
        return await _cached(
            f"robust:{int(args.get('min_providers', 2))}:{float(args.get('tukey_k', 1.5))}",
            lambda: _build_aggregator().robust_quorum_aggregate(
                int(args.get("min_providers", 2)),
                float(args.get("tukey_k", 1.5)),
            ),
        )
    raise ValueError(f"unknown tool: {name}")


@app.post("/mcp")
async def mcp_endpoint(req: Request) -> JSONResponse:
    """MCP streamable-http transport. JSON-RPC 2.0. Implements:
    - initialize
    - tools/list
    - tools/call
    Claude Desktop / Cursor / any MCP client can point at this URL."""
    _metrics["mcp_requests_total"] += 1
    try:
        payload = await req.json()
    except Exception:
        return JSONResponse(_mcp_error(None, -32700, "parse error"), status_code=400)
    req_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params") or {}

    if method == "initialize":
        return JSONResponse({
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "protocolVersion": _MCP_PROTOCOL_VERSION,
                "serverInfo": {"name": "africa-oracle", "version": VERSION},
                "capabilities": {"tools": {}},
            },
        })
    if method == "tools/list":
        return JSONResponse({
            "jsonrpc": "2.0", "id": req_id,
            "result": {"tools": _MCP_TOOLS},
        })
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            result = await _mcp_call_tool(name, args)
            return JSONResponse(_mcp_text_result(req_id, result))
        except ValueError as e:
            return JSONResponse(_mcp_error(req_id, -32602, str(e)))
        except KeyError as e:
            return JSONResponse(_mcp_error(req_id, -32602, f"missing argument: {e}"))
    return JSONResponse(_mcp_error(req_id, -32601, f"method not found: {method}"))


# ─── /changelog — Article-schema HTML of CHANGELOG.md ────────────────────────
_CHANGELOG_PATH = REPO_ROOT / "CHANGELOG.md"


def _markdown_to_html(md: str) -> str:
    """Tiny dep-free Markdown→HTML pass. Handles the subset Keep-a-Changelog
    uses: # headings, * bullets, `code`, [links](url), bold/italic."""
    import html as _html
    import re
    out_lines: list[str] = []
    in_list = False
    for raw in md.splitlines():
        line = _html.escape(raw, quote=False)
        line = re.sub(r"`([^`]+)`", r"<code>\1</code>", line)
        line = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', line)
        line = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", line)
        if line.startswith("### "):
            if in_list: out_lines.append("</ul>"); in_list = False
            out_lines.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("## "):
            if in_list: out_lines.append("</ul>"); in_list = False
            out_lines.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("# "):
            if in_list: out_lines.append("</ul>"); in_list = False
            out_lines.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("- ") or line.startswith("* "):
            if not in_list: out_lines.append("<ul>"); in_list = True
            out_lines.append(f"<li>{line[2:]}</li>")
        elif line.strip() == "":
            if in_list: out_lines.append("</ul>"); in_list = False
            out_lines.append("")
        else:
            if in_list: out_lines.append("</ul>"); in_list = False
            out_lines.append(f"<p>{line}</p>")
    if in_list: out_lines.append("</ul>")
    return "\n".join(out_lines)


@app.get("/changelog", response_class=HTMLResponse)
def changelog() -> HTMLResponse:
    """CHANGELOG.md rendered with Article JSON-LD so AI search tools
    can index version history as a citable artifact."""
    _metrics["seo_requests_total"] += 1
    if not _CHANGELOG_PATH.exists():
        raise HTTPException(status_code=404)
    md = _CHANGELOG_PATH.read_text(encoding="utf-8")
    body_html = _markdown_to_html(md)
    jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": f"Africa Oracle · Changelog (v{VERSION})",
        "description": "Version history and release notes.",
        "author": {"@type": "Organization", "name": "Africa Oracle contributors"},
        "datePublished": "2026-11-08",
        "dateModified": datetime.utcnow().strftime("%Y-%m-%d"),
        "url": f"{_PUBLIC_ORIGIN}/changelog",
    })
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>Africa Oracle · Changelog</title>'
        '<meta name="description" content="Version history for Africa Oracle.">'
        f'<link rel="canonical" href="{_PUBLIC_ORIGIN}/changelog">'
        '<meta name="robots" content="index,follow,max-snippet:-1">'
        f'<script type="application/ld+json">{jsonld}</script>'
        '<style>'
        ':root{--bg:#f6f8fb;--fg:#0b1220;--muted:#5c6473;--card:#fff;--border:#e5e9f0;--accent:#d97706}'
        '@media(prefers-color-scheme:dark){:root{--bg:#0b1220;--fg:#e6ebf5;--muted:#8b93a7;--card:#131b2e;--border:#1f2a44;--accent:#f59e0b}}'
        'body{margin:0;padding:40px 20px;font:16px/1.6 -apple-system,BlinkMacSystemFont,system-ui,sans-serif;background:var(--bg);color:var(--fg);max-width:760px;margin-inline:auto}'
        'h1{margin:0 0 4px;font-size:22px}h2{margin:28px 0 8px;font-size:17px}h3{margin:16px 0 6px;font-size:14px;color:var(--muted)}'
        'ul{padding-left:20px}li{margin:4px 0}code{background:var(--card);border:1px solid var(--border);padding:1px 6px;border-radius:4px;font-size:13px}'
        'a{color:var(--accent)}p{color:var(--fg)}nav{margin-top:40px;padding-top:20px;border-top:1px solid var(--border);font-size:13px;color:var(--muted)}'
        '</style></head><body>'
        f'{body_html}'
        '<nav><a href="/">dashboard</a> · <a href="/faq">FAQ</a> · '
        '<a href="/docs">API docs</a> · <a href="https://github.com/nzengou/africa-oracle-agent">source</a></nav>'
        '</body></html>'
    )
    return HTMLResponse(html)


_started = time.time()
