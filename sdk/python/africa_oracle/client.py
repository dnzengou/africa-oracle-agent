"""HTTP client for the Africa Oracle API.

ARM64-native (pure Python, no compiled wheels). Resilient:
- timeout on every call (default 10s)
- typed dataclass responses
- raises OracleError on non-2xx instead of silent zero
"""

from __future__ import annotations

import os
import urllib.error
import urllib.request
import json
from dataclasses import dataclass
from typing import Any

DEFAULT_BASE_URL = os.environ.get(
    "AFRICA_ORACLE_URL", "https://africa-oracle.fly.dev"
)
DEFAULT_TIMEOUT = float(os.environ.get("AFRICA_ORACLE_TIMEOUT", "10"))


class OracleError(RuntimeError):
    """Raised for any non-2xx, timeout, or parse failure."""


@dataclass(frozen=True)
class PriceFeed:
    provider: str
    country: str
    currency: str
    buy_price: float
    sell_price: float
    mid_price: float
    spread_bps: float
    volume_24h: float
    confidence: float
    timestamp: int


@dataclass(frozen=True)
class QuorumReport:
    oracle_id: str
    timestamp: int
    currencies: int
    prices: list[dict]
    quorum_failed: list[dict]


class Client:
    """Synchronous HTTP client. Stateless — safe to share across threads."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(self, path: str, body: dict | None = None) -> Any:
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST" if body is not None else "GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            raise OracleError(f"{e.code} {e.reason} @ {path}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            raise OracleError(f"network: {e} @ {path}") from e
        except json.JSONDecodeError as e:
            raise OracleError(f"invalid JSON @ {path}") from e

    def health(self) -> dict:
        return self._request("/health")

    def providers(self) -> dict:
        return self._request("/providers")

    def hunt(self, provider: str, country: str, simulate: bool = True) -> PriceFeed:
        r = self._request(
            "/hunt",
            {"provider": provider, "country": country, "simulate": simulate},
        )
        return PriceFeed(
            provider=r["provider"],
            country=r["country"],
            currency=r["currency"],
            buy_price=r["buy_price"],
            sell_price=r["sell_price"],
            mid_price=r["mid_price"],
            spread_bps=r["spread_bps"],
            volume_24h=r["volume_24h"],
            confidence=r["confidence"],
            timestamp=r["timestamp"],
        )

    def feeds_all(self) -> dict:
        return self._request("/feeds/all", {})

    def feeds_quorum(self, min_providers: int = 2) -> QuorumReport:
        r = self._request("/feeds/quorum", {"min_providers": min_providers})
        return QuorumReport(
            oracle_id=r["oracle_id"],
            timestamp=r["timestamp"],
            currencies=r["currencies"],
            prices=r["prices"],
            quorum_failed=r.get("quorum_failed", []),
        )
