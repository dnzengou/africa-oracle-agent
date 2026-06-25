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


# ─── Tukey-fence outlier filter (Resilient pillar — manipulation defense) ────


def test_tukey_bounds_drops_obvious_outlier():
    """Classic textbook case: 7 clustered values + 1 wild outlier → outlier
    falls outside the fence."""
    lo, hi = OracleAggregator._tukey_bounds(
        [100.0, 101.0, 99.0, 100.5, 99.5, 100.2, 100.8, 5000.0]
    )
    assert lo < 100 < hi
    assert hi < 5000  # outlier rejected


def test_tukey_bounds_skips_small_samples():
    """Fewer than 4 samples → IQR is meaningless; return open bounds."""
    lo, hi = OracleAggregator._tukey_bounds([100.0, 200.0, 50.0])
    assert lo == float("-inf")
    assert hi == float("inf")


def test_tukey_bounds_keeps_clustered_feeds():
    """All clustered within IQR → both bounds accept the cluster."""
    vals = [150.0, 150.1, 149.9, 150.2, 149.8, 150.05]
    lo, hi = OracleAggregator._tukey_bounds(vals)
    for v in vals:
        assert lo <= v <= hi


def test_robust_quorum_runs_end_to_end():
    """Smoke-test the full pipeline: feeds in, prices + outliers_dropped out."""
    agg = OracleAggregator()
    agg.add_agent(OracleAgent("safaricom", "KE"))
    agg.add_agent(OracleAgent("airtel", "KE"))
    agg.add_agent(OracleAgent("safaricom", "TZ"))  # TZS, only safaricom
    out = agg.robust_quorum_aggregate(min_providers=2, tukey_k=1.5)
    assert out["quorum_threshold"] == 2
    assert out["tukey_k"] == 1.5
    assert "outliers_dropped" in out
    assert isinstance(out["outliers_dropped"], list)
    assert out["agents_kept"] <= out["agents_reporting"]
    currencies = {p["currency"] for p in out["prices"]}
    assert "KES" in currencies   # 2 providers, passes quorum
    assert "TZS" not in currencies  # only 1 provider, fails quorum
    failed = {p["currency"] for p in out["quorum_failed"]}
    assert "TZS" in failed


def test_robust_quorum_drops_planted_outlier():
    """Inject a synthetic outlier directly into a feed group via a stub agent
    and confirm robust_quorum_aggregate filters it out before consensus."""

    class StubAgent:
        def __init__(self, feed):
            self._feed = feed
            self.agent_id = feed.get("agent_id", "stub")

        def fetch_price(self):
            return self._feed

    base_feed = {
        "provider": "Test", "provider_slug": "t",
        "country": "XX", "currency": "TST",
        "timestamp": 0, "datetime": "2026-01-01T00:00:00+00:00",
        "spread": 0.005, "spread_bps": 50,
        "volume_24h": 1_000_000, "confidence": 0.9,
        "sources": 100, "agent_id": "a", "simulated": True,
    }

    def feed(provider, mid, agent_id):
        return {**base_feed, "provider": provider, "agent_id": agent_id,
                "buy_price": mid * 0.998, "sell_price": mid * 1.002,
                "mid_price": mid}

    agg = OracleAggregator()
    # 7 clustered around 100 + 1 wild outlier at 1000 (realistic multi-agent
    # density — see _tukey_bounds() docstring on N≥6 reliability)
    cluster = [
        ("MTN-A", 100.0), ("MTN-B", 99.9),
        ("Safaricom-A", 100.5), ("Safaricom-B", 100.1),
        ("Airtel", 99.8),
        ("Orange-A", 100.2), ("Orange-B", 100.3),
        ("Compromised", 1000.0),
    ]
    for i, (prov, mid) in enumerate(cluster):
        agg.agents.append(StubAgent(feed(prov, mid, f"a{i}")))

    out = agg.robust_quorum_aggregate(min_providers=2, tukey_k=1.5)
    # The wild outlier must be dropped
    dropped_providers = {o["provider"] for o in out["outliers_dropped"]}
    assert "Compromised" in dropped_providers
    # Consensus mid_price must be near the cluster, not skewed by the outlier
    tst = next(p for p in out["prices"] if p["currency"] == "TST")
    assert 99.0 < tst["mid_price"] < 101.0
    assert tst["agent_count"] == 7  # outlier excluded


def test_api_robust_endpoint():
    from fastapi.testclient import TestClient

    from api.app import app

    client = TestClient(app)
    r = client.post("/feeds/robust", json={"min_providers": 2, "tukey_k": 1.5})
    assert r.status_code == 200
    body = r.json()
    assert body["quorum_threshold"] == 2
    assert body["tukey_k"] == 1.5
    assert isinstance(body["prices"], list)
    assert isinstance(body["outliers_dropped"], list)
    assert "agents_kept" in body


def test_api_robust_rejects_invalid_tukey():
    from fastapi.testclient import TestClient

    from api.app import app

    client = TestClient(app)
    # tukey_k above the upper bound (3.0)
    r = client.post("/feeds/robust", json={"min_providers": 2, "tukey_k": 10})
    assert r.status_code == 422
