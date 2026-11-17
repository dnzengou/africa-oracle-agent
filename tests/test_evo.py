"""Tests for evo_oracle.py — genome evolution, weighted consensus, persistence."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evo_oracle import (
    AGREE_BONUS,
    FITNESS_MAX,
    FITNESS_MIN,
    FITNESS_START,
    OUTLIER_PENALTY,
    QUARANTINE_BELOW,
    RECOVER_ABOVE,
    EvoOracle,
    evolved_robust_aggregate,
    weighted_median,
)
from oracle_agent import OracleAgent, OracleAggregator


def _feed(slug="safaricom", country="KE", ccy="KES", mid=150.0):
    return {
        "provider_slug": slug, "provider": slug.title(), "country": country,
        "currency": ccy, "mid_price": mid, "buy_price": mid - 1,
        "sell_price": mid + 1,
    }


# ─── weighted_median ──────────────────────────────────────────────────────────


def test_weighted_median_basic():
    assert weighted_median([(1.0, 1), (2.0, 1), (3.0, 1)]) == 2.0


def test_weighted_median_weight_dominates():
    # 10.0 carries 90% of the weight → it is the weighted median
    assert weighted_median([(1.0, 1), (10.0, 9)]) == 10.0


def test_weighted_median_ignores_zero_weight():
    assert weighted_median([(1.0, 0), (5.0, 3)]) == 5.0


def test_weighted_median_empty_returns_none():
    assert weighted_median([]) is None
    assert weighted_median([(1.0, 0)]) is None


# ─── genome evolution ─────────────────────────────────────────────────────────


def test_fresh_source_starts_neutral():
    evo = EvoOracle(data_dir=None)
    assert evo.weight_for("safaricom:KE") == FITNESS_START


def test_agreement_raises_fitness_integer():
    evo = EvoOracle(data_dir=None)
    evo.observe({"KES": [_feed()]}, [])
    fitness = evo.genome["safaricom:KE"]["fitness_bps"]
    assert fitness == FITNESS_START + AGREE_BONUS
    assert isinstance(fitness, int)


def test_outlier_penalized():
    evo = EvoOracle(data_dir=None)
    evo.observe({}, [_feed(mid=999.0)])
    assert evo.genome["safaricom:KE"]["fitness_bps"] == FITNESS_START + OUTLIER_PENALTY


def test_fitness_clamped_at_bounds():
    evo = EvoOracle(data_dir=None)
    for _ in range(50):
        evo.observe({}, [_feed()])
    assert evo.genome["safaricom:KE"]["fitness_bps"] == FITNESS_MIN
    evo2 = EvoOracle(data_dir=None)
    for _ in range(100):
        evo2.observe({"KES": [_feed()]}, [])
    assert evo2.genome["safaricom:KE"]["fitness_bps"] == FITNESS_MAX


def test_quarantine_and_recovery_hysteresis():
    evo = EvoOracle(data_dir=None)
    while evo.genome.get("safaricom:KE", {"fitness_bps": FITNESS_START})["fitness_bps"] >= QUARANTINE_BELOW:
        evo.observe({}, [_feed()])
    assert evo.genome["safaricom:KE"]["quarantined"] is True
    assert evo.weight_for("safaricom:KE") == 0
    # agreement signals climb it back over RECOVER_ABOVE → re-enabled
    while evo.genome["safaricom:KE"]["fitness_bps"] < RECOVER_ABOVE:
        evo.observe({"KES": [_feed()]}, [])
    assert evo.genome["safaricom:KE"]["quarantined"] is False
    assert evo.weight_for("safaricom:KE") > 0


def test_trajectories_accumulate():
    evo = EvoOracle(data_dir=None)
    evo.observe({"KES": [_feed(), _feed(slug="airtel")]}, [_feed(slug="mtn", country="GH", ccy="GHS")])
    assert evo.trajectories_total == 3


# ─── persistence ──────────────────────────────────────────────────────────────


def test_persistence_roundtrip(tmp_path):
    d = str(tmp_path / "evo")
    evo = EvoOracle(data_dir=d)
    evo.observe({"KES": [_feed()]}, [])
    reloaded = EvoOracle(data_dir=d)
    assert reloaded.genome["safaricom:KE"]["fitness_bps"] == FITNESS_START + AGREE_BONUS
    assert reloaded.trajectories_total == 1
    lines = (tmp_path / "evo" / "trajectories.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["source"] == "safaricom:KE"


def test_memory_only_mode_never_touches_disk(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    evo = EvoOracle(data_dir=None)
    evo.observe({"KES": [_feed()]}, [])
    assert evo.memory_only is True
    assert list(tmp_path.iterdir()) == []


# ─── evolved aggregation ──────────────────────────────────────────────────────


def _aggregator():
    agg = OracleAggregator()
    for slug, country in [("safaricom", "KE"), ("airtel", "KE"),
                          ("mtn", "GH"), ("safaricom", "GH")]:
        agg.add_agent(OracleAgent(slug, country, simulate=True))
    return agg


def test_evolved_aggregate_shape_and_evo_block():
    evo = EvoOracle(data_dir=None)
    result = evolved_robust_aggregate(_aggregator(), evo, min_providers=2)
    assert result["currencies"] >= 1
    assert result["evo"]["trajectories_total"] > 0
    assert result["evo"]["memory_only"] is True
    for p in result["prices"]:
        assert p["weighted"] is True
        assert p["distinct_providers"] >= 2


def test_evolved_falls_back_when_all_quarantined():
    evo = EvoOracle(data_dir=None)
    # Force-quarantine every source, then aggregate: prices must still publish.
    for slug, country in [("safaricom", "KE"), ("airtel", "KE"),
                          ("mtn", "GH"), ("safaricom", "GH")]:
        evo.genome[f"{slug}:{country}"] = {
            "fitness_bps": 0, "runs": 1, "quarantined": True, "updated": 0,
        }
    result = evolved_robust_aggregate(_aggregator(), evo, min_providers=1)
    assert result["currencies"] >= 1
    # weighted median had no weight to work with → unweighted fallback
    assert all(p["weighted"] is False for p in result["prices"])


# ─── API surface ──────────────────────────────────────────────────────────────


def test_api_feeds_evolved():
    from fastapi.testclient import TestClient
    from api.app import app

    client = TestClient(app)
    r = client.post("/feeds/evolved", json={"min_providers": 2, "tukey_k": 1.5})
    assert r.status_code == 200
    body = r.json()
    assert "evo" in body
    assert body["evo"]["trajectories_total"] > 0


def test_api_evo_genome():
    from fastapi.testclient import TestClient
    from api.app import app

    client = TestClient(app)
    r = client.get("/evo/genome")
    assert r.status_code == 200
    body = r.json()
    assert "trajectories_total" in body
    assert "genome" in body


def test_api_rates_map():
    from fastapi.testclient import TestClient
    from api.app import app

    client = TestClient(app)
    r = client.get("/rates")
    assert r.status_code == 200
    body = r.json()
    assert body["base"] == "USD"
    assert "KES" in body["rates"]
    assert body["rates"]["KES"]["mid"] > 0


def test_api_rates_with_conversion():
    from fastapi.testclient import TestClient
    from api.app import app

    client = TestClient(app)
    r = client.get("/rates", params={"from": "KES", "to": "NGN", "amount": 1000})
    assert r.status_code == 200
    conv = r.json()["conversion"]
    assert conv["to"]["currency"] == "NGN"
    assert conv["to"]["amount"] > 0


def test_api_rates_rejects_unknown_currency():
    from fastapi.testclient import TestClient
    from api.app import app

    client = TestClient(app)
    r = client.get("/rates", params={"from": "ZZZ", "to": "KES", "amount": 10})
    assert r.status_code == 400
