"""Tests for oracle_agent.py — provider/country mapping, simulation, aggregation."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oracle_agent import PROVIDERS, REFERENCE_RATES, OracleAgent, OracleAggregator


# ─── Provider configuration ──────────────────────────────────────────────────


def test_four_providers_registered():
    assert set(PROVIDERS.keys()) == {"safaricom", "airtel", "orange", "mtn"}


@pytest.mark.parametrize("slug", ["safaricom", "airtel", "orange", "mtn"])
def test_provider_has_required_fields(slug):
    p = PROVIDERS[slug]
    assert "name" in p and isinstance(p["name"], str)
    assert "countries" in p and len(p["countries"]) >= 1
    assert "currency" in p
    assert p["agent_count"] > 0
    for country in p["countries"]:
        assert country in p["currency"], f"{slug}/{country} missing currency"


def test_every_currency_has_reference_rate():
    for p in PROVIDERS.values():
        for ccy in p["currency"].values():
            assert ccy in REFERENCE_RATES, f"missing rate: {ccy}"


# ─── OracleAgent ─────────────────────────────────────────────────────────────


def test_agent_rejects_unknown_provider():
    with pytest.raises(ValueError):
        OracleAgent("zelle", "US")


def test_agent_rejects_unsupported_country():
    with pytest.raises(ValueError):
        OracleAgent("safaricom", "ZZ")


def test_agent_simulates_price():
    a = OracleAgent("safaricom", "KE", simulate=True)
    feed = a.fetch_price()
    assert feed["currency"] == "KES"
    assert feed["country"] == "KE"
    assert feed["simulated"] is True
    assert feed["buy_price"] > 0
    assert feed["sell_price"] > feed["buy_price"]
    assert 0 < feed["spread"] < 0.5
    assert 0 < feed["confidence"] <= 0.99
    assert len(feed["agent_id"]) == 16


def test_real_fetch_not_implemented():
    a = OracleAgent("mtn", "GH", simulate=False)
    with pytest.raises(NotImplementedError):
        a.fetch_price()


# ─── Aggregator ──────────────────────────────────────────────────────────────


def test_aggregator_empty_returns_error():
    agg = OracleAggregator()
    out = agg.aggregate()
    assert "error" in out


def test_aggregator_consensus_per_currency():
    agg = OracleAggregator()
    agg.add_agent(OracleAgent("safaricom", "KE"))
    agg.add_agent(OracleAgent("airtel", "KE"))
    out = agg.aggregate()
    assert out["agents_reporting"] == 2
    kes = [c for c in out["prices"] if c["currency"] == "KES"]
    assert len(kes) == 1
    assert kes[0]["agent_count"] == 2
    assert kes[0]["buy_price"] > 0


def test_aggregator_groups_xof_across_orange_countries():
    agg = OracleAggregator()
    for country in ("CI", "SN", "ML"):
        agg.add_agent(OracleAgent("orange", country))
    out = agg.aggregate()
    xof = [c for c in out["prices"] if c["currency"] == "XOF"]
    assert len(xof) == 1
    assert xof[0]["agent_count"] == 3
    assert set(xof[0]["countries"]) == {"CI", "SN", "ML"}


def test_aggregator_volume_weighted_spread_in_range():
    agg = OracleAggregator()
    agg.add_agent(OracleAgent("mtn", "NG"))
    out = agg.aggregate()
    ngn = next(c for c in out["prices"] if c["currency"] == "NGN")
    assert 0 < ngn["spread"] < 0.05  # < 5%


# ─── Quorum (Resilient pillar) ───────────────────────────────────────────────


def test_quorum_drops_single_provider_currencies():
    """A currency with only one provider must NOT pass quorum=2."""
    agg = OracleAggregator()
    agg.add_agent(OracleAgent("mtn", "NG"))  # NGN only on mtn → 1 provider
    agg.add_agent(OracleAgent("safaricom", "KE"))
    agg.add_agent(OracleAgent("airtel", "KE"))  # KES has 2 providers
    out = agg.quorum_aggregate(min_providers=2)
    currencies_passed = {p["currency"] for p in out["prices"]}
    currencies_failed = {p["currency"] for p in out["quorum_failed"]}
    assert "KES" in currencies_passed
    assert "NGN" in currencies_failed
    assert out["quorum_threshold"] == 2


def test_quorum_one_admits_everything():
    agg = OracleAggregator()
    agg.add_agent(OracleAgent("mtn", "NG"))
    out = agg.quorum_aggregate(min_providers=1)
    assert len(out["prices"]) == 1
    assert out["quorum_failed"] == []


def test_quorum_empty_input():
    out = OracleAggregator().quorum_aggregate(min_providers=2)
    assert "error" in out


# ─── FastAPI endpoint smoke (Resilient + Scalable + Affordable) ─────────────


def test_api_health_and_metrics():
    from fastapi.testclient import TestClient

    from api.app import app

    client = TestClient(app)

    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["providers"] == 4

    r = client.get("/metrics")
    assert r.status_code == 200
    assert "africa_oracle_info" in r.text
    assert 'version="' in r.text


def test_api_quorum_endpoint():
    from fastapi.testclient import TestClient

    from api.app import app

    client = TestClient(app)
    r = client.post("/feeds/quorum", json={"min_providers": 2})
    assert r.status_code == 200
    body = r.json()
    assert body["quorum_threshold"] == 2
    assert isinstance(body["prices"], list)
    assert isinstance(body["quorum_failed"], list)


def test_api_hunt_rejects_unknown_provider():
    from fastapi.testclient import TestClient

    from api.app import app

    client = TestClient(app)
    r = client.post("/hunt", json={"provider": "zelle", "country": "US"})
    assert r.status_code == 400
