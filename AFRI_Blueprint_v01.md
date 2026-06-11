### Africa Oracle Extraction Agent (AFRI)

The **Africa Oracle Extraction Agent (AFRI)** is a sovereign, resilient, and edge-optimized data network designed to power a native alternative to foreign fiat-backed stablecoins. By transforming over 45,000 localized mobile money agents into distributed price-oracle nodes, the platform extracts real-time, localized buy/sell spreads across approximately 30 African nations.

---

### Core Pillars & Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ Mobile Money APIs (M-Pesa, Airtel, Orange, MTN)                 │
└──────────────────────────────┬──────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│ Oracle Extraction Agents (Py / Go / Sh; one per provider×country)│
│   - poll APIs every 30s · Default Simulator Mode                │
└──────────────────────────────┬──────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│ Aggregation Layer (median price, vol-weighted spread, quorum)   │
└──────────────────────────────┬──────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│ Price Feed API (FastAPI ASGI · Async /feeds · SSE Stream)        │
└──────────────────────────────┬──────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│ AFRI Bridge (afri-bridge.sh) → afri-token.fc (TON Jetton)         │
│   mint: momo deposit + ref → verify → mint AFRI                  │
│   burn: burn AFRI → momo payout                                  │
└─────────────────────────────────────────────────────────────────┘

```

The system is engineered around five fundamental design principles:

* **Resilient:** Implements an on-chain/off-chain quorum aggregation mechanism (`quorum_aggregate(min_providers=2)`). This ensures that a single-provider outage cannot artificially distort or manipulate currency rates.
* **Sovereign:** Prioritizes African operational control by utilizing self-hosted `docker-compose` frameworks tailored for local VPS operators, open-source FunC smart contracts, and dedicated multi-arch configurations targeting Fly.io's Johannesburg (`jnb`) cloud region.
* **Scalable:** Built with a stateless API architecture supporting async parallel retrieval (`/feeds/all`) and Server-Sent Events (SSE) via `/feeds/stream` for real-time pushing.
* **Affordable:** Formulated to run efficiently on ultra-low-cost, $35 edge hardware (such as a Raspberry Pi utilizing a POSIX shell port) without relying on heavyweight database dependencies like Redis or Postgres.
* **Alternative Settlement:** Serves as a mobile-money-native collateral layer to back the **AFRI Jetton**—a TIP-74 stablecoin on the TON blockchain. It bypasses typical foreign-currency bottlenecks using low-gas TON ledger transactions ($0.005) integrated directly into Telegram via TON Connect.

---

### Supported Networks & Tokenomics

The network standardizes tracking across major telecommunications infrastructure providers:

| Provider | Supported Countries | Active Currencies | Est. Agent Nodes | Status |
| --- | --- | --- | --- | --- |
| **Safaricom M-Pesa** | KE, TZ, UG, RW, ZA, GH, CD, LS, MZ, SO | KES, TZS, UGX, RWF, ZAR, GHS, CDF, LSL, MZN, SOS | ~15,000 | Planned (Simulated) |
| **Airtel Money** | KE, UG, RW, ZA, CD, NE, GA, CG, TD | KES, UGX, RWF, ZAR, CDF, XOF, XAF | ~8,000 | Planned (Simulated) |
| **Orange Money** | CI, SN, ML, BF, NE, BJ, TG, CM, MG | XOF, XAF, MGA | ~12,000 | Planned (Simulated) |
| **MTN MoMo** | GH, UG, RW, ZA, CI, NG, CM, ZM | GHS, UGX, RWF, ZAR, XOF, NGN, XAF, ZMW | ~10,000 | Planned (Simulated) |

The aggregated real-time price feeds act as a secure mint/burn heartbeat for the **AFRI Jetton**. Mobile money deposits trigger an automated verification that mints the token, while burning the token triggers local mobile money payouts. To guard against volatility, the stablecoin is structurally **over-collateralized at 120%** using verifiable mobile-money reserves.

---

### API Surface & System Deployment

The application features a flexible polyglot deployment model (Python, Go, and POSIX Shell), exposing an ASGI-compliant FastAPI layer:

* `GET /health` & `GET /providers`: Monitors network uptime, metadata mappings, and operational health.
* `POST /feeds/quorum`: Enforces strict threshold consensus across multi-provider endpoints to mitigate single-point manipulation.
* `GET /feeds/stream`: Streams continuous volumetric and price telemetry to client consumers.
* `GET /metrics`: Outflow node telemetry formatted natively for Prometheus monitoring.

**Cost Model:** Dev-testing runs on completely free cloud tiers (Fly.io shared-cpu / Vercel hobby). Scaled production tracking (spanning 10 providers across 30 countries polling at 30-second intervals) is highly optimized to run at approximately **$5,000/month**.