# AFRI Sovereignty & Value Proposition

> **Mission:** A resilient, sovereign, scalable, affordable alternative to foreign fiat-backed stablecoins — for Africa, by African mobile-money rails.

## Why now

USDT and USDC together hold ~95% of stablecoin liquidity, but both are:
- **Custodied in US jurisdictions** (Tether HQ in BVI; Circle HQ in Boston). African users carry US-Treasury counterparty risk on every transfer.
- **Settled on chains optimized for high-fee L1s** (Ethereum gas ≫ a typical M-Pesa fee). Sub-dollar African remittances are economically unviable.
- **Banking-rail dependent** for on/off-ramps. Every African user must touch a US dollar correspondent bank to mint/redeem — the exact rail African mobile money was built to bypass.

AFRI is the inverse: mobile-money native, TON-settled (fractions of a cent per TX), and collateralized by reserves held in African mobile-money systems.

---

## The five pillars

### 1. Resilient
- **Quorum aggregation** (`/feeds/quorum`, `min_providers ≥ 2`): a single-provider outage (e.g. Safaricom API down) cannot move the published rate. Currencies that fail quorum are listed in `quorum_failed`, not silently filled.
- **Polyglot oracle** (Py / Go / Sh): if the Python runtime or container fleet has a regression, the Go binary and POSIX shell port can keep publishing from edge nodes (PicoClaw, Raspberry Pi).
- **No single-region dependency**: the API is stateless and deployable to any region. Default target is Fly.io `jnb` (Johannesburg), with `cpt` (Cape Town) and `nbo` (Nairobi) as recommended secondaries.
- **Reference-rate fallback** in `afri-bridge.sh` ensures the mint/burn path never blocks on oracle freshness — it degrades to a wider spread instead of hanging.

### 2. Sovereign
- **No US/EU jurisdictional dependency** in the deploy path. Primary region `jnb` (South Africa). Recommended secondaries are all African. GHCR is a transport layer for the image, not a runtime dependency — the same image runs anywhere.
- **Self-host path** (`docker-compose.yml`): any African operator can run the oracle on a $5/mo VPS (Hetzner Frankfurt → African colos as they mature). No SaaS dependency.
- **Data residency**: the oracle holds no PII. Only public rate data crosses the wire. KYC stays at the mobile-money provider boundary.
- **Open-source FunC contract** (`afri-token.fc`): collateral math is on-chain, auditable, and amendable by community governance. No off-chain "trust us" component.
- **TON over Ethereum/Solana**: TON is the only major chain with first-class Telegram integration — the dominant messaging app in West and East Africa.

### 3. Scalable
- **Async parallel aggregation**: `/feeds/all` and `/feeds/quorum` run aggregation in a worker thread so the event loop stays responsive. Single Fly machine handles ~200 RPS soft limit.
- **SSE streaming** (`/feeds/stream`): consumers (DEX price ticker, trading bot, alert service) subscribe once and receive deltas — no per-poll HTTP overhead. Linear cost in connections, not request volume.
- **Stateless API**: horizontal scale is `fly scale count 5` — no Redis, no Postgres, no shared state. Each machine is independent.
- **Multi-arch container**: `linux/amd64` for cloud, `linux/arm64` for African colos and Raspberry Pi edge nodes. Both built from the same Dockerfile.

### 4. Affordable
- **Free-tier deployable**: Fly.io shared-cpu-1x with 512 MB is free for low-traffic apps. Cold-start to first response in <2 s.
- **No external dependencies at runtime**: `requirements.txt` is `fastapi + uvicorn + pydantic`. No Redis, no Postgres, no Sentry, no APM agent. Smaller image = cheaper egress.
- **PicoClaw / Raspberry Pi edge path**: the POSIX shell port runs on $35 hardware. An African operator with no cloud budget can still publish to the network.
- **TON gas**: a mint TX costs ~$0.005 — three orders of magnitude cheaper than the same on Ethereum mainnet.
- **No KYC vendor lock-in**: when KYC is needed in Phase 2, it happens at the mobile-money provider (M-Pesa, MTN MoMo) — which has already done it. AFRI does not pay for re-KYC.

### 5. Alternative (to USDT / USDC)

| Dimension | USDT | USDC | **AFRI** |
|---|---|---|---|
| **Backing** | Mixed (CP, Treasury bills) | US Treasury bills | African mobile-money reserves, 120% over-collateralized |
| **Custody jurisdiction** | BVI / Hong Kong | USA (NYDFS) | Distributed across mobile-money providers per currency |
| **Settlement chain** | Tron (cheap) / Ethereum | Ethereum / Solana | TON (fractions of a cent per TX) |
| **Min on-ramp** | ~$10 via exchange | ~$10 via exchange | ~$0.50 via M-Pesa agent (no exchange) |
| **Settlement to mobile money** | 2–5 day SWIFT chain | 2–5 day SWIFT chain | Direct, ~seconds via bridge |
| **Regulatory exposure** | OFAC, NYDFS, BVI FSC | OFAC, NYDFS | African regulators only (Bank of Ghana, CBN, CBK, BCEAO, BEAC) |
| **Reserve audit** | Quarterly attestation | Monthly attestation | On-chain collateral ratio (real-time `get_collateral_ratio`) |
| **Native messenger integration** | None | None | Telegram via TON Connect |

---

## Quality gate: R²S² + 5 pillars

Every change is reviewed against:

| Axis | Definition | Quick check |
|---|---|---|
| Robust | Graceful failure | All I/O has timeout + error path |
| Reliable | Predictable | `pytest tests/ -v` is 14/14 green |
| Solid | Complete | No half-implementations behind feature flags |
| Stable | Backwards-compatible | API surface unchanged across patch versions |
| Resistant | Fault-tolerant | Quorum aggregation; fallback rates |
| Scalable | Linear cost | Stateless; multi-arch; async I/O |
| Secure | No exposed surface | No secrets, no shell injection, validated inputs |
| Systematic | Convention-following | Blueprint updated; changelog entry; lineage tracked |
| **Resilient** *(pillar)* | Single-provider outage doesn't move the rate | `/feeds/quorum?min_providers=2` |
| **Sovereign** *(pillar)* | African jurisdictional + operational control | Deploy region in `{jnb, cpt, nbo, ...}` |
| **Scalable** *(pillar)* | Edge + cloud both viable | Multi-arch image + shell port |
| **Affordable** *(pillar)* | Free-tier viable for solo operator | Image < 200 MB; no paid deps |
| **Alternative** *(pillar)* | Better than USDT/USDC on African settlement | See comparison table |

---

## Operator on-ramp (self-host)

```sh
# On any VPS with Docker (1 vCPU / 512 MB / $4–6/mo)
git clone https://github.com/<owner>/africa-oracle-agent
cd africa-oracle-agent
docker compose up -d
curl http://localhost:8000/health
```

That's it. No Redis, no Postgres, no signup form. The operator owns the data path.
