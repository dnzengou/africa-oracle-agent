"""FastAPI ASGI wrapper around oracle_agent.py.

Endpoints:
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

from oracle_agent import PROVIDERS, OracleAgent, OracleAggregator, convert_amount  # noqa: E402

VERSION = "0.8.0"
CACHE_TTL_S = 10
RATE_LIMIT_PER_MIN = 60
REPO_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"
DASHBOARD_PATH = STATIC_DIR / "index.html"

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
    "rate_requests_total": 0,
    "widget_requests_total": 0,
    "seo_requests_total": 0,
    "cache_hits_total": 0,
    "cache_misses_total": 0,
    "rate_limited_total": 0,
}


# ─── TTL cache (simple, in-process) ──────────────────────────────────────────
_cache: dict[str, tuple[float, dict]] = {}


async def _cached(key: str, fn) -> dict:
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < CACHE_TTL_S:
        _metrics["cache_hits_total"] += 1
        return hit[1]
    _metrics["cache_misses_total"] += 1
    value = await asyncio.to_thread(fn)
    _cache[key] = (now, value)
    return value


# ─── Rate limiting (per-IP token-bucket, in-process) ─────────────────────────
_rate_buckets: dict[str, deque] = defaultdict(deque)


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    path = request.url.path
    if (path in ("/health", "/metrics", "/", "/llms.txt", "/ai.txt", "/widget.js",
                 "/robots.txt", "/sitemap.xml", "/feed.xml", "/faq", "/mcp.json")
            or path.startswith("/static")
            or path.startswith("/.well-known/")
            or path.startswith("/openapi")
            or path.startswith("/docs")
            or path.startswith("/redoc")):
        return await call_next(request)
    ip = request.client.host if request.client else "?"
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
@app.get("/", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    if DASHBOARD_PATH.exists():
        html = DASHBOARD_PATH.read_text(encoding="utf-8").replace("{{VERSION}}", VERSION)
        return HTMLResponse(html)
    return HTMLResponse(
        f"<h1>Africa Oracle {VERSION}</h1><p>API is running. See <a href='/docs'>/docs</a>.</p>"
    )


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
    result = await _cached(
        f"robust:{req.min_providers}:{req.tukey_k}",
        lambda: _build_aggregator().robust_quorum_aggregate(
            req.min_providers, req.tukey_k
        ),
    )
    _metrics["feeds_quorum_failed_total"] += len(result.get("quorum_failed", []))
    _metrics["feeds_outliers_dropped_total"] += len(result.get("outliers_dropped", []))
    return result


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
_WIDGET_JS = """(function(){
  var S=document.currentScript, D=S?S.dataset:{};
  var FROM=(D.from||'KES').toUpperCase(), TO=(D.to||'NGN').toUpperCase();
  var AMOUNT=parseFloat(D.amount||'100');
  var API=D.api||(new URL(S.src)).origin;
  var THEME=D.theme||'auto';
  var id='afri-'+Math.random().toString(36).slice(2,9);
  var el=document.createElement('div');el.id=id;
  el.setAttribute('role','status');el.setAttribute('aria-live','polite');
  var dark=(THEME==='dark')||(THEME==='auto'&&matchMedia&&matchMedia('(prefers-color-scheme: dark)').matches);
  el.style.cssText='display:inline-flex;gap:8px;align-items:center;padding:8px 12px;'+
    'border-radius:8px;font:500 13px/1.3 ui-monospace,Menlo,monospace;'+
    'background:'+(dark?'#131b2e':'#fff')+';color:'+(dark?'#e6ebf5':'#0b1220')+';'+
    'border:1px solid '+(dark?'#1f2a44':'#e5e9f0')+';';
  el.innerHTML='<span style="opacity:.6">loading…</span>';
  if(S&&S.parentNode) S.parentNode.insertBefore(el,S.nextSibling);
  function fmt(n,d){return new Intl.NumberFormat(undefined,{maximumFractionDigits:d,minimumFractionDigits:d}).format(n);}
  function load(){
    fetch(API+'/convert',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({from:FROM,to:TO,amount:AMOUNT,side:'mid'})})
      .then(function(r){return r.json();})
      .then(function(r){
        if(r.detail){el.innerHTML='<span style=\"color:#dc2626\">'+r.detail+'</span>';return;}
        var dot='<span style=\"width:6px;height:6px;border-radius:50%;background:#16a34a;display:inline-block\"></span>';
        el.innerHTML=dot+' '+fmt(AMOUNT,2)+' '+FROM+' = <b>'+fmt(r.to.amount,2)+' '+TO+'</b>'+
          ' <span style=\"opacity:.6\">· '+fmt(r.confidence*100,0)+'% conf</span>';
      })
      .catch(function(){el.innerHTML='<span style=\"color:#dc2626\">unavailable</span>';});
  }
  load(); setInterval(load,30000);
})();
"""


@app.get("/widget.js")
def widget_js() -> Response:
    """Embeddable widget. Usage:
        <script src="https://africa-oracle.fly.dev/widget.js"
                data-from="KES" data-to="NGN" data-amount="100"></script>
    """
    _metrics["widget_requests_total"] += 1
    return Response(
        _WIDGET_JS,
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
_FAQ = [
    ("What is Africa Oracle?",
     "A resilient price oracle that aggregates live mobile-money FX rates from M-Pesa, Airtel Money, Orange Money, and MTN MoMo across about 30 African countries into a quorum-protected, outlier-filtered median rate. It is Phase 0 of the AFRI Jetton stablecoin on TON (TIP-74)."),
    ("Which currencies are supported?",
     "KES, TZS, UGX, RWF, ZAR, GHS, CDF, LSL, MZN, SOS, XOF, XAF, MGA, NGN, ZMW. USD is supported as a base currency. The ground truth is the REFERENCE_RATES constant in oracle_agent.py."),
    ("Is the oracle using real provider APIs?",
     "Not yet. In the current version the --simulate path is the default and only mode. The _real_fetch() method raises NotImplementedError. Real API integration is Phase 1 and requires provider API keys at the provider boundary."),
    ("How do I get a rate for USD to Kenyan shillings?",
     "GET https://africa-oracle.fly.dev/rate/USD/KES. The response contains rate, confidence, spread_bps, and the list of providers backing the quote."),
    ("How do I embed live rates on my site?",
     "One line of JS: <script src=\"https://africa-oracle.fly.dev/widget.js\" data-from=\"KES\" data-to=\"NGN\" data-amount=\"100\"></script>. See INTEGRATE.md for Next.js, React, Python, Node, and SSE examples."),
    ("What is the rate limit?",
     "60 requests per minute per IP on data endpoints. Static surfaces (/, /widget.js, /llms.txt, /ai.txt, /.well-known/*, /openapi.json, /docs, /redoc) are unlimited."),
    ("What is the Tukey-fence outlier filter?",
     "A classical statistical fence: values outside Q1 - 1.5*IQR and Q3 + 1.5*IQR are rejected. It defends the published median against a single compromised provider trying to sway the rate."),
    ("Is this project centralized?",
     "The oracle is self-hostable on any African VPS via docker-compose. The TON Jetton smart contract (afri-token.fc) is open source. The maintained public deployment is one instance; others can run their own and compare with /metrics."),
    ("Can I use this in production?",
     "For simulated data: yes, immediately. For production financial decisions that require live mobile-money rates, wait for Phase 1 real-API integration or self-host with your own provider credentials."),
    ("How do AI agents use this?",
     "Three ways: (1) read /.well-known/ai-plugin.json and call the OpenAPI schema; (2) read /mcp.json and register the tools with an MCP client like Claude Desktop; (3) read /.well-known/agents.json for agent-to-agent discovery."),
    ("Where do the simulated prices come from?",
     "REFERENCE_RATES in oracle_agent.py are hand-bootstrapped seeds. The simulator adds Gaussian noise proportional to provider density plus a volume-of-day multiplier. See the _simulate_price method for the full model."),
    ("What is the AFRI Jetton?",
     "A TIP-74 fungible token on the TON blockchain, intended to be 120% over-collateralized by mobile-money reserves. The contract scaffold is in afri-token.fc. It is not deployed to mainnet. See AFRI_Blueprint.md for the roadmap."),
    ("How is this different from USDT or USDC on African payment rails?",
     "USDT/USDC are USD-backed stablecoins. AFRI aims to be mobile-money-native, priced directly against African local currencies through this oracle. The comparison is documented in SOVEREIGNTY.md."),
    ("Who maintains this project?",
     "It is open source. See CONTRIBUTING.md to contribute, CITATION.cff for citation metadata, and SECURITY.md for the responsible-disclosure policy."),
    ("How can I verify a claim about this project?",
     "Every public claim maps to a file or function in the repository. See FACTS.md for the ledger."),
]


@app.get("/faq", response_class=HTMLResponse)
def faq() -> HTMLResponse:
    """FAQ page with FAQPage JSON-LD — big LLM citation surface."""
    _metrics["seo_requests_total"] += 1
    qa_rows = "".join(
        f'<details><summary>{q}</summary><p>{a}</p></details>'
        for q, a in _FAQ
    )
    jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q,
             "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in _FAQ
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
    ]
    for key, val in _metrics.items():
        lines.append(f"# TYPE africa_oracle_{key} counter")
        lines.append(f"africa_oracle_{key} {val}")
    return "\n".join(lines) + "\n"


_started = time.time()
