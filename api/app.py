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

VERSION = "0.7.0"
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
    if (path in ("/health", "/metrics", "/", "/llms.txt", "/ai.txt", "/widget.js")
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
        return HTMLResponse(DASHBOARD_PATH.read_text(encoding="utf-8"))
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
