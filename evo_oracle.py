#!/usr/bin/env python3
"""EvoOracle — self-evolving provider-fitness layer (the EvoMetaClaw flywheel).

Every aggregation run is captured as a trajectory signal: how far each
provider×country feed deviated from the robust consensus, and whether it was
flagged as an outlier. Signals evolve an integer-basis-point fitness genome
per feed source; consensus is then a fitness-weighted median, and sources
whose fitness collapses are quarantined (still scored in shadow mode so they
can recover, but excluded from the published price).

Why this is the moat: a competitor can copy the provider registry and the
reference rates in an afternoon. They cannot copy the accumulated trajectory
log or the genome distilled from it — oracle quality becomes a function of
operating history, and every run widens the gap.

Design constraints (R²S²):
- stdlib only — runs everywhere oracle_agent.py runs
- fitness/weights are integers in basis points (0..10000) — no float in the
  scoring path
- persistence degrades gracefully: read-only filesystems (e.g. serverless)
  fall back to in-memory genome without failing a request
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

FITNESS_START = 5000      # neutral
FITNESS_MAX = 10000
FITNESS_MIN = 0
QUARANTINE_BELOW = 2000   # weight → 0, excluded from published consensus
RECOVER_ABOVE = 3500      # hysteresis: must climb back above this to re-enter
AGREE_BAND_BPS = 50       # |deviation| ≤ band counts as agreement
AGREE_BONUS = 120
DISAGREE_PENALTY = -150
OUTLIER_PENALTY = -900


def weighted_median(pairs: list[tuple[float, int]]) -> float | None:
    """Lower weighted median of (value, integer_weight) pairs.

    Zero-weight pairs are ignored; returns None if nothing carries weight.
    """
    pairs = sorted(p for p in pairs if p[1] > 0)
    if not pairs:
        return None
    total = sum(w for _, w in pairs)
    acc = 0
    for value, weight in pairs:
        acc += weight
        if acc * 2 >= total:
            return value
    return pairs[-1][0]


class EvoOracle:
    """Per-source fitness genome + append-only trajectory log."""

    def __init__(self, data_dir: str | None = "evo-data"):
        self.data_dir = Path(data_dir) if data_dir else None
        self.memory_only = self.data_dir is None
        self.genome: dict[str, dict] = {}
        self.trajectories_total = 0
        self._load()

    # ─── persistence ────────────────────────────────────────────────────────

    def _genome_path(self) -> Path:
        return self.data_dir / "genome.json"

    def _trajectory_path(self) -> Path:
        return self.data_dir / "trajectories.jsonl"

    def _load(self) -> None:
        if self.memory_only:
            return
        try:
            raw = json.loads(self._genome_path().read_text(encoding="utf-8"))
            self.genome = raw.get("genome", {})
            self.trajectories_total = int(raw.get("trajectories_total", 0))
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as e:
            print(f"EvoOracle: genome load failed, starting fresh: {e}", file=sys.stderr)

    def _persist(self, records: list[dict]) -> None:
        if self.memory_only:
            return
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            with open(self._trajectory_path(), "a", encoding="utf-8") as f:
                for r in records:
                    f.write(json.dumps(r, separators=(",", ":")) + "\n")
            tmp = self._genome_path().with_suffix(".tmp")
            tmp.write_text(json.dumps(
                {"genome": self.genome, "trajectories_total": self.trajectories_total},
                separators=(",", ":"),
            ), encoding="utf-8")
            os.replace(tmp, self._genome_path())
        except OSError as e:
            # Read-only filesystem (serverless) or disk pressure: keep evolving
            # in memory rather than failing the feed.
            self.memory_only = True
            print(f"EvoOracle: disk unavailable, memory-only mode: {e}", file=sys.stderr)

    # ─── genome ─────────────────────────────────────────────────────────────

    def _entry(self, key: str) -> dict:
        if key not in self.genome:
            self.genome[key] = {
                "fitness_bps": FITNESS_START, "runs": 0,
                "quarantined": False, "updated": 0,
            }
        return self.genome[key]

    def weight_for(self, key: str) -> int:
        entry = self.genome.get(key)
        if entry is None:
            return FITNESS_START
        return 0 if entry["quarantined"] else entry["fitness_bps"]

    def _apply_signal(self, key: str, signal: int, now: int) -> int:
        entry = self._entry(key)
        fitness = max(FITNESS_MIN, min(FITNESS_MAX, entry["fitness_bps"] + signal))
        entry["fitness_bps"] = fitness
        entry["runs"] += 1
        entry["updated"] = now
        if entry["quarantined"]:
            if fitness >= RECOVER_ABOVE:
                entry["quarantined"] = False
        elif fitness < QUARANTINE_BELOW:
            entry["quarantined"] = True
        return fitness

    # ─── observation ────────────────────────────────────────────────────────

    def observe(self, kept_by_ccy: dict[str, list[dict]],
                outliers: list[dict]) -> list[dict]:
        """Score one aggregation round and evolve the genome.

        kept_by_ccy: feeds that survived the outlier fence, grouped by currency.
        outliers: dropped feeds (need provider_slug/country/currency/mid_price).
        Scoring truth is the unweighted median of kept feeds — scoring against
        the weighted median would let high-fitness sources reinforce themselves.
        """
        now = int(time.time())
        records = []

        for ccy, feeds in kept_by_ccy.items():
            mids = sorted(f["mid_price"] for f in feeds)
            consensus = mids[len(mids) // 2]
            for f in feeds:
                deviation_bps = int(abs(f["mid_price"] - consensus) / consensus * 10000)
                signal = AGREE_BONUS if deviation_bps <= AGREE_BAND_BPS else DISAGREE_PENALTY
                key = f"{f['provider_slug']}:{f['country']}"
                fitness = self._apply_signal(key, signal, now)
                records.append({
                    "ts": now, "source": key, "currency": ccy,
                    "mid_price": f["mid_price"], "deviation_bps": deviation_bps,
                    "outlier": False, "fitness": fitness,
                })

        for o in outliers:
            key = f"{o['provider_slug']}:{o['country']}"
            fitness = self._apply_signal(key, OUTLIER_PENALTY, now)
            records.append({
                "ts": now, "source": key, "currency": o["currency"],
                "mid_price": o["mid_price"], "deviation_bps": None,
                "outlier": True, "fitness": fitness,
            })

        self.trajectories_total += len(records)
        self._persist(records)
        return records

    def stats(self) -> dict:
        quarantined = sorted(k for k, v in self.genome.items() if v["quarantined"])
        return {
            "trajectories_total": self.trajectories_total,
            "sources": len(self.genome),
            "quarantined": quarantined,
            "memory_only": self.memory_only,
            "genome": self.genome,
        }


def evolved_robust_aggregate(aggregator, evo: EvoOracle,
                             min_providers: int = 2,
                             tukey_k: float = 1.5) -> dict:
    """Tukey-fence filter → trajectory capture → fitness-weighted consensus.

    Same shape as OracleAggregator.robust_quorum_aggregate plus an `evo` block,
    with mid/buy/sell computed as fitness-weighted medians. If every source for
    a currency is quarantined, falls back to the unweighted robust consensus —
    the oracle never goes dark because the genome got strict.
    """
    prices = aggregator._collect_prices()
    if not prices:
        return {"error": "no prices collected", "timestamp": int(time.time())}

    kept_by_ccy: dict[str, list[dict]] = {}
    outliers: list[dict] = []
    for ccy, feeds in aggregator._group_by_currency(prices).items():
        lo, hi = aggregator._tukey_bounds([f["mid_price"] for f in feeds], k=tukey_k)
        for f in feeds:
            if lo <= f["mid_price"] <= hi:
                kept_by_ccy.setdefault(ccy, []).append(f)
            else:
                outliers.append({
                    "provider_slug": f["provider_slug"], "provider": f["provider"],
                    "country": f["country"], "currency": ccy,
                    "mid_price": f["mid_price"],
                    "bound_lo": round(lo, 4), "bound_hi": round(hi, 4),
                })

    evo.observe(kept_by_ccy, outliers)

    consensus = []
    for ccy, feeds in kept_by_ccy.items():
        base = aggregator._consensus_for_currency(ccy, feeds)
        weighted = [
            (f["mid_price"], f["buy_price"], f["sell_price"],
             evo.weight_for(f"{f['provider_slug']}:{f['country']}"))
            for f in feeds
        ]
        mid = weighted_median([(m, w) for m, _, _, w in weighted])
        if mid is not None:
            base["mid_price"] = round(mid, 4)
            buy = weighted_median([(b, w) for _, b, _, w in weighted])
            sell = weighted_median([(s, w) for _, _, s, w in weighted])
            base["buy_price"] = round(buy, 4)
            base["sell_price"] = round(sell, 4)
        base["weighted"] = mid is not None
        consensus.append(base)

    passed, failed = [], []
    for p in consensus:
        distinct = len(set(p["providers"]))
        (passed if distinct >= min_providers else failed).append(
            {**p, "distinct_providers": distinct}
        )

    stats = evo.stats()
    return {
        "timestamp": int(time.time()),
        "quorum_threshold": min_providers,
        "tukey_k": tukey_k,
        "currencies": len(passed),
        "agents_reporting": len(prices),
        "agents_kept": sum(len(v) for v in kept_by_ccy.values()),
        "prices": passed,
        "quorum_failed": [
            {"currency": p["currency"], "distinct_providers": p["distinct_providers"]}
            for p in failed
        ],
        "outliers_dropped": outliers,
        "evo": {
            "trajectories_total": stats["trajectories_total"],
            "sources": stats["sources"],
            "quarantined": stats["quarantined"],
            "memory_only": stats["memory_only"],
        },
    }
