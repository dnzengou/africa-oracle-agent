"""FastAPI ASGI wrapper around oracle_agent.py.

Endpoints:
  GET  /health        — liveness + version + provider count
  GET  /providers     — provider/country/currency map
  POST /hunt          — single feed: {provider, country, simulate}
  POST /feeds/all     — aggregated feed (median + vol-weighted spread)
  POST /feeds/quorum  — resilient feed: only currencies with ≥ min_providers
  GET  /feeds/stream  — Server-Sent Events: aggregate every interval seconds
  GET  /metrics       — Prometheus text format: oracle counters
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oracle_agent import PROVIDERS, OracleAgent, OracleAggregator  # noqa: E402

VERSION = "0.3.0"

app = FastAPI(
    title="Africa Oracle Extraction Agent",
    version=VERSION,
    description="Resilient, sovereign, scalable mobile-money price oracle for African stablecoins.",
)


class HuntRequest(BaseModel):
    provider: str = Field(..., description="safaricom | airtel | orange | mtn")
    country: str = Field(..., description="ISO 3166-1 alpha-2, e.g. KE, NG")
    simulate: bool = Field(default=True, description="Use simulated feed (default)")


class QuorumRequest(BaseModel):
    min_providers: int = Field(default=2, ge=1, le=4)


# ─── In-process counters (Prometheus-style) ──────────────────────────────────
_metrics = {
    "hunt_requests_total": 0,
    "hunt_errors_total": 0,
    "feeds_all_requests_total": 0,
    "feeds_quorum_requests_total": 0,
    "feeds_stream_connections_total": 0,
    "feeds_quorum_failed_total": 0,
}


def _build_aggregator() -> OracleAggregator:
    agg = OracleAggregator()
    for slug, info in PROVIDERS.items():
        for country in info["countries"]:
            try:
                agg.add_agent(OracleAgent(slug, country, simulate=True))
            except ValueError:
                continue
    return agg


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
    # Aggregate in a worker thread so the event loop stays responsive
    return await asyncio.to_thread(_build_aggregator().aggregate)


@app.post("/feeds/quorum")
async def feeds_quorum(req: QuorumRequest) -> dict:
    _metrics["feeds_quorum_requests_total"] += 1
    result = await asyncio.to_thread(
        _build_aggregator().quorum_aggregate, req.min_providers
    )
    _metrics["feeds_quorum_failed_total"] += len(result.get("quorum_failed", []))
    return result


async def _sse_loop(interval: int) -> AsyncGenerator[bytes, None]:
    _metrics["feeds_stream_connections_total"] += 1
    while True:
        data = await asyncio.to_thread(_build_aggregator().aggregate)
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
    """SSE stream — affordable scale path (no per-poll HTTP overhead)."""
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
