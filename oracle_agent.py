#!/usr/bin/env python3
"""
Africa Oracle Extraction Agent v0.1.0

Extracts real-time price feeds from mobile money aggregator APIs.
Each agent polls one provider in one country and reports buy/sell prices.

Phase 0: Oracle Bootstrapping for African Stablecoins.

Usage:
    python3 oracle_agent.py --provider safaricom --country KE
    python3 oracle_agent.py --provider mtn --country GH --simulate

Output: JSON to stdout (or file with --output)
"""

import argparse
import hashlib
import json
import os
import random
import statistics
import sys
import time
from datetime import datetime, timezone

# ─── Provider Configuration ───────────────────────────────────────────────────

PROVIDERS = {
    "safaricom": {
        "name": "Safaricom M-Pesa",
        "countries": ["KE", "TZ", "UG", "RW", "ZA", "GH", "CD", "LS", "MZ", "SO"],
        "currency": {"KE": "KES", "TZ": "TZS", "UG": "UGX", "RW": "RWF",
                     "ZA": "ZAR", "GH": "GHS", "CD": "CDF", "LS": "LSL",
                     "MZ": "MZN", "SO": "SOS"},
        "api_endpoint": "https://api.safaricom.co.ke/mpesa/v1/prices",
        "agent_count": 15000,  # approximate active agents
    },
    "airtel": {
        "name": "Airtel Money",
        "countries": ["KE", "UG", "RW", "ZA", "CD", "NE", "GA", "CG", "TD"],
        "currency": {"KE": "KES", "UG": "UGX", "RW": "RWF", "ZA": "ZAR",
                     "CD": "CDF", "NE": "XOF", "GA": "XAF", "CG": "XAF",
                     "TD": "XAF"},
        "api_endpoint": "https://api.airtel.africa/money/v1/prices",
        "agent_count": 8000,
    },
    "orange": {
        "name": "Orange Money",
        "countries": ["CI", "SN", "ML", "BF", "NE", "BJ", "TG", "CM", "MG"],
        "currency": {"CI": "XOF", "SN": "XOF", "ML": "XOF", "BF": "XOF",
                     "NE": "XOF", "BJ": "XOF", "TG": "XOF", "CM": "XAF",
                     "MG": "MGA"},
        "api_endpoint": "https://api.orange.com/money/v1/prices",
        "agent_count": 12000,
    },
    "mtn": {
        "name": "MTN MoMo",
        "countries": ["GH", "UG", "RW", "ZA", "CI", "NG", "CM", "ZM"],
        "currency": {"GH": "GHS", "UG": "UGX", "RW": "RWF", "ZA": "ZAR",
                     "CI": "XOF", "NG": "NGN", "CM": "XAF", "ZM": "ZMW"},
        "api_endpoint": "https://api.mtn.com/momo/v1/prices",
        "agent_count": 10000,
    },
}

# ─── Reference Exchange Rates (USD base, approximate) ────────────────────────

# These are bootstrapped from public sources.
# In production, these come from the mobile money API directly.

REFERENCE_RATES = {
    "KES": 150.25, "TZS": 2500.00, "UGX": 3800.00, "RWF": 1350.00,
    "ZAR": 18.50,  "GHS": 14.80,   "CDF": 2800.00, "LSL": 18.50,
    "MZN": 64.00,  "SOS": 570.00,  "XOF": 610.00,  "XAF": 610.00,
    "MGA": 4600.00,"NGN": 1550.00, "ZMW": 25.00,
}

# ─── Oracle Agent ─────────────────────────────────────────────────────────────

class OracleAgent:
    """Extracts price data from a mobile money provider in one country."""

    def __init__(self, provider: str, country: str, simulate: bool = True):
        if provider not in PROVIDERS:
            raise ValueError(f"Unknown provider: {provider}. Choose: {list(PROVIDERS.keys())}")
        self.slug = provider
        self.provider = PROVIDERS[provider]
        self.country = country
        self.currency = self.provider["currency"].get(country)
        if not self.currency:
            raise ValueError(f"Country {country} not supported by {provider}")
        self.simulate = simulate
        # nanosecond clock + random nonce avoids collision when many agents start in same second
        nonce = f"{provider}:{country}:{time.time_ns()}:{os.urandom(4).hex()}"
        self.agent_id = hashlib.sha256(nonce.encode()).hexdigest()[:16]

    def fetch_price(self) -> dict:
        """Fetch or simulate price data from mobile money API."""
        if self.simulate:
            return self._simulate_price()
        return self._real_fetch()

    def _simulate_price(self) -> dict:
        """Simulate price extraction with realistic spreads and noise."""
        base_rate = REFERENCE_RATES.get(self.currency, 1000.0)

        # Spread varies by liquidity — more agents = tighter spread
        agent_density = self.provider["agent_count"] / 15000.0
        base_spread = 0.005 / agent_density  # 0.3%-1.5% spread

        # Add random noise (market volatility)
        noise = random.gauss(0, base_rate * 0.002)  # 0.2% std dev
        spread_noise = random.gauss(0, base_spread * 0.3)

        buy_price = base_rate - (base_rate * base_spread / 2) + noise
        sell_price = base_rate + (base_rate * base_spread / 2) + noise
        spread = (sell_price - buy_price) / buy_price + spread_noise

        # Simulate volume (proportional to agent count and time of day)
        hour = datetime.now(timezone.utc).hour
        # Peak hours: 8-12, 14-18 Africa time (UTC+2/3)
        africa_hour = (hour + 2) % 24
        volume_mult = 1.0
        if 8 <= africa_hour <= 12:
            volume_mult = 2.0
        elif 14 <= africa_hour <= 18:
            volume_mult = 2.5
        elif 22 <= africa_hour or africa_hour <= 5:
            volume_mult = 0.3

        volume_24h = random.uniform(500000, 50000000) * volume_mult * agent_density

        return {
            "provider": self.provider["name"],
            "provider_slug": self.slug,
            "country": self.country,
            "currency": self.currency,
            "timestamp": int(time.time()),
            "datetime": datetime.now(timezone.utc).isoformat(),
            "buy_price": round(buy_price, 4),
            "sell_price": round(sell_price, 4),
            "mid_price": round((buy_price + sell_price) / 2, 4),
            "spread": round(spread, 6),
            "spread_bps": round(spread * 10000, 2),  # basis points
            "volume_24h": round(volume_24h, 2),
            "confidence": round(min(0.99, 0.85 + agent_density * 0.1), 4),
            "sources": random.randint(50, int(self.provider["agent_count"] * 0.01)),
            "agent_id": self.agent_id,
            "simulated": True,
        }

    def _real_fetch(self) -> dict:
        """Real API fetch (placeholder — requires API keys)."""
        raise NotImplementedError(
            "Real API fetch requires provider API keys. "
            "Use --simulate for development."
        )


# ─── Aggregation Layer ────────────────────────────────────────────────────────

class OracleAggregator:
    """Aggregates price feeds from multiple agents into a consensus oracle."""

    def __init__(self):
        self.agents: list[OracleAgent] = []
        self.last_prices: list[dict] = []

    def add_agent(self, agent: OracleAgent):
        self.agents.append(agent)

    def aggregate(self) -> dict:
        """Collect prices from all agents and compute consensus."""
        prices = []
        for agent in self.agents:
            try:
                price = agent.fetch_price()
                prices.append(price)
            except Exception as e:
                print(f"Agent {agent.agent_id} failed: {e}", file=sys.stderr)

        if not prices:
            return {"error": "no prices collected", "timestamp": int(time.time())}

        self.last_prices = prices

        # Group by currency
        by_currency = {}
        for p in prices:
            ccy = p["currency"]
            if ccy not in by_currency:
                by_currency[ccy] = []
            by_currency[ccy].append(p)

        # Compute consensus per currency
        consensus = []
        for ccy, feeds in by_currency.items():
            buy_prices = [f["buy_price"] for f in feeds]
            sell_prices = [f["sell_price"] for f in feeds]
            volumes = [f["volume_24h"] for f in feeds]
            confidences = [f["confidence"] for f in feeds]
            sources = [f["sources"] for f in feeds]

            # True median (averages the two middle values for even-length lists)
            median_buy = statistics.median(buy_prices)
            median_sell = statistics.median(sell_prices)

            # Volume-weighted spread
            total_vol = sum(volumes)
            weighted_spread = sum(
                f["spread"] * (f["volume_24h"] / total_vol) for f in feeds
            ) if total_vol > 0 else 0

            consensus.append({
                "currency": ccy,
                "countries": list(set(f["country"] for f in feeds)),
                "providers": list(set(f["provider"] for f in feeds)),
                "buy_price": round(median_buy, 4),
                "sell_price": round(median_sell, 4),
                "mid_price": round((median_buy + median_sell) / 2, 4),
                "spread": round(weighted_spread, 6),
                "spread_bps": round(weighted_spread * 10000, 2),
                "total_volume_24h": round(total_vol, 2),
                "avg_confidence": round(sum(confidences) / len(confidences), 4),
                "total_sources": sum(sources),
                "agent_count": len(feeds),
            })

        return {
            "oracle_id": hashlib.sha256(
                f"africa-oracle:{int(time.time())}".encode()
            ).hexdigest()[:16],
            "timestamp": int(time.time()),
            "datetime": datetime.now(timezone.utc).isoformat(),
            "currencies": len(consensus),
            "agents_reporting": len(prices),
            "prices": consensus,
            "raw_feeds": prices,  # In production: omit for efficiency
        }

    def quorum_aggregate(self, min_providers: int = 2) -> dict:
        """Resilient variant of aggregate() — only publishes prices for currencies
        where at least `min_providers` distinct providers reported. Currencies that
        fail quorum are dropped from `prices` but listed in `quorum_failed` so the
        consumer can detect a partition (e.g. M-Pesa outage in KE)."""
        base = self.aggregate()
        if "prices" not in base:
            return base
        passed, failed = [], []
        for p in base["prices"]:
            distinct = len(set(p["providers"]))
            (passed if distinct >= min_providers else failed).append(
                {**p, "distinct_providers": distinct}
            )
        return {
            **base,
            "quorum_threshold": min_providers,
            "currencies": len(passed),
            "prices": passed,
            "quorum_failed": [
                {"currency": p["currency"], "distinct_providers": p["distinct_providers"]}
                for p in failed
            ],
        }

    # ─── Tukey-fence outlier detection (Resilient pillar — manipulation defense) ─

    @staticmethod
    def _tukey_bounds(values: list[float], k: float = 1.5) -> tuple[float, float]:
        """Returns (lo, hi) — values outside the IQR-fence are outliers.

        Tukey's fence: lo = Q1 - k*IQR, hi = Q3 + k*IQR. With k=1.5 this is the
        classical box-plot whisker. With fewer than 4 samples IQR is not
        meaningful, so we return open bounds (no filtering).

        Caveat for small N: with N=5 and a single large outlier, that outlier
        contaminates Q3 (since the upper half is only 2 values), which widens
        the fence enough to let the outlier through. The filter is reliable
        from N≥6 onward; in production each currency typically has 8+ feeds
        across providers × countries × agents, where this is non-issue.
        """
        if len(values) < 4:
            return (float("-inf"), float("inf"))
        sorted_v = sorted(values)
        n = len(sorted_v)
        lower_half = sorted_v[: n // 2]
        upper_half = sorted_v[(n + 1) // 2 :]
        q1 = statistics.median(lower_half)
        q3 = statistics.median(upper_half)
        iqr = q3 - q1
        return (q1 - k * iqr, q3 + k * iqr)

    def robust_quorum_aggregate(self, min_providers: int = 2,
                                  tukey_k: float = 1.5) -> dict:
        """Quorum + outlier-resistant variant — applies a Tukey-fence filter on
        mid_price per currency BEFORE consensus, then enforces quorum on the
        surviving providers. Defends against a single compromised provider
        publishing a wild price to sway the median.

        Returns the same shape as quorum_aggregate() plus an `outliers_dropped`
        array listing every (currency, provider, country, mid_price) tuple that
        fell outside the IQR fence.
        """
        prices = []
        for agent in self.agents:
            try:
                prices.append(agent.fetch_price())
            except Exception as e:
                print(f"Agent {agent.agent_id} failed: {e}", file=sys.stderr)

        if not prices:
            return {"error": "no prices collected", "timestamp": int(time.time())}

        by_currency: dict[str, list[dict]] = {}
        for p in prices:
            by_currency.setdefault(p["currency"], []).append(p)

        kept_feeds: list[dict] = []
        outliers: list[dict] = []
        for ccy, feeds in by_currency.items():
            mids = [f["mid_price"] for f in feeds]
            lo, hi = self._tukey_bounds(mids, k=tukey_k)
            for f in feeds:
                if lo <= f["mid_price"] <= hi:
                    kept_feeds.append(f)
                else:
                    outliers.append({
                        "currency": ccy,
                        "provider": f["provider"],
                        "country": f["country"],
                        "mid_price": f["mid_price"],
                        "bound_lo": round(lo, 4),
                        "bound_hi": round(hi, 4),
                    })

        # Re-aggregate from the filtered set using the standard pipeline
        scratch = OracleAggregator()
        scratch.last_prices = kept_feeds
        # Reuse aggregate()'s per-currency consensus logic by injecting kept feeds
        # via a tiny shim: build the by_currency map and rerun the consensus path.
        passed_consensus: list[dict] = []
        kept_by_ccy: dict[str, list[dict]] = {}
        for f in kept_feeds:
            kept_by_ccy.setdefault(f["currency"], []).append(f)
        for ccy, feeds in kept_by_ccy.items():
            buy_prices = [f["buy_price"] for f in feeds]
            sell_prices = [f["sell_price"] for f in feeds]
            volumes = [f["volume_24h"] for f in feeds]
            confidences = [f["confidence"] for f in feeds]
            sources = [f["sources"] for f in feeds]
            median_buy = statistics.median(buy_prices)
            median_sell = statistics.median(sell_prices)
            total_vol = sum(volumes)
            weighted_spread = (
                sum(f["spread"] * (f["volume_24h"] / total_vol) for f in feeds)
                if total_vol > 0 else 0
            )
            passed_consensus.append({
                "currency": ccy,
                "countries": list(set(f["country"] for f in feeds)),
                "providers": list(set(f["provider"] for f in feeds)),
                "buy_price": round(median_buy, 4),
                "sell_price": round(median_sell, 4),
                "mid_price": round((median_buy + median_sell) / 2, 4),
                "spread": round(weighted_spread, 6),
                "spread_bps": round(weighted_spread * 10000, 2),
                "total_volume_24h": round(total_vol, 2),
                "avg_confidence": round(sum(confidences) / len(confidences), 4),
                "total_sources": sum(sources),
                "agent_count": len(feeds),
            })

        passed, failed = [], []
        for p in passed_consensus:
            distinct = len(set(p["providers"]))
            (passed if distinct >= min_providers else failed).append(
                {**p, "distinct_providers": distinct}
            )

        return {
            "oracle_id": hashlib.sha256(
                f"africa-oracle-robust:{int(time.time())}".encode()
            ).hexdigest()[:16],
            "timestamp": int(time.time()),
            "datetime": datetime.now(timezone.utc).isoformat(),
            "quorum_threshold": min_providers,
            "tukey_k": tukey_k,
            "currencies": len(passed),
            "agents_reporting": len(prices),
            "agents_kept": len(kept_feeds),
            "prices": passed,
            "quorum_failed": [
                {"currency": p["currency"], "distinct_providers": p["distinct_providers"]}
                for p in failed
            ],
            "outliers_dropped": outliers,
        }


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Africa Oracle Extraction Agent — Mobile Money Price Feeds"
    )
    parser.add_argument("--provider", choices=list(PROVIDERS.keys()),
                        help="Mobile money provider")
    parser.add_argument("--country", help="Country code (e.g., KE, NG, GH)")
    parser.add_argument("--all", action="store_true",
                        help="Run all provider/country combinations")
    parser.add_argument("--simulate", action="store_true", default=True,
                        help="Simulate price data (default: True)")
    parser.add_argument("--output", help="Output file (default: stdout)")
    parser.add_argument("--interval", type=int, default=0,
                        help="Polling interval in seconds (0 = one-shot)")
    parser.add_argument("--pretty", action="store_true",
                        help="Pretty-print JSON output")

    args = parser.parse_args()

    # Build agent list
    aggregator = OracleAggregator()

    if args.all:
        for provider_name, provider_info in PROVIDERS.items():
            for country in provider_info["countries"]:
                try:
                    agent = OracleAgent(provider_name, country, simulate=args.simulate)
                    aggregator.add_agent(agent)
                except ValueError as e:
                    print(f"Skipping {provider_name}/{country}: {e}", file=sys.stderr)
    elif args.provider and args.country:
        agent = OracleAgent(args.provider, args.country, simulate=args.simulate)
        aggregator.add_agent(agent)
    else:
        parser.print_help()
        sys.exit(1)

    # Run
    def print_output(data: dict):
        output = json.dumps(data, indent=2 if args.pretty else None, default=str)
        if args.output:
            with open(args.output, "a") as f:
                f.write(output + "\n")
        else:
            print(output)

    if args.interval > 0:
        try:
            while True:
                data = aggregator.aggregate()
                print_output(data)
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nShutting down.", file=sys.stderr)
    else:
        data = aggregator.aggregate()
        print_output(data)


if __name__ == "__main__":
    main()
