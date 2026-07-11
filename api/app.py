"""FastAPI ASGI wrapper around oracle_agent.py.

Endpoints:
  GET  /                — dashboard UI (single-page, self-contained)
  GET  /health          — liveness + version + provider count
  GET  /providers       — provider/country/currency map
  POST /hunt            — single feed: {provider, country, simulate}
  POST /feeds/all       — aggregated feed (median + vol-weighted spread)
  POST /feeds/quorum    — resilient feed: only currencies with ≥ min_providers
  POST /feeds/robust    — quorum + Tukey-fence outlier filter
  POST /convert         — cross-currency conversion (from, to, amount, side)
  GET  /feeds/stream    — Server-Sent Events: aggregate every interval seconds
  GET  /metrics         — Prometheus text format: oracle counters
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
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oracle_agent import PROVIDERS, OracleAgent, OracleAggregator, convert_amount  # noqa: E402

VERSION = "0.6.0"
CACHE_TTL_S = 10
RATE_LIMIT_PER_MIN = 60
DASHBOARD_PATH = Path(__file__).resolve().parent / "static" / "index.html"

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
    if request.url.path in ("/health", "/metrics", "/") or request.url.path.startswith("/static"):
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
