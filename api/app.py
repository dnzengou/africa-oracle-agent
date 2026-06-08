"""FastAPI ASGI wrapper around oracle_agent.py.

Endpoints:
  GET  /health
  GET  /providers
  POST /hunt        body: {provider, country, simulate}
  POST /feeds/all   body: {}
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# Make oracle_agent.py importable when api/ is a subdirectory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oracle_agent import PROVIDERS, OracleAgent, OracleAggregator  # noqa: E402

VERSION = "0.2.0"

app = FastAPI(
    title="Africa Oracle Extraction Agent",
    version=VERSION,
    description="Real-time mobile money price feeds across Africa.",
)


class HuntRequest(BaseModel):
    provider: str = Field(..., description="safaricom | airtel | orange | mtn")
    country: str = Field(..., description="ISO 3166-1 alpha-2, e.g. KE, NG")
    simulate: bool = Field(default=True, description="Use simulated feed (default)")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": VERSION, "providers": len(PROVIDERS)}


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
    try:
        agent = OracleAgent(req.provider, req.country, simulate=req.simulate)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        return agent.fetch_price()
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))


@app.post("/feeds/all")
def feeds_all() -> dict:
    agg = OracleAggregator()
    for slug, info in PROVIDERS.items():
        for country in info["countries"]:
            try:
                agg.add_agent(OracleAgent(slug, country, simulate=True))
            except ValueError:
                continue
    return agg.aggregate()
