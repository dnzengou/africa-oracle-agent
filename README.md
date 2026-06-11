# Africa Oracle Extraction Agent

> **A resilient, sovereign, scalable, affordable alternative to foreign fiat-backed stablecoins.**
> Phase 0 of the AFRI Jetton (TIP-74 on TON) — mobile-money-native price oracle for ~30 African countries.

[![tests](https://img.shields.io/badge/tests-20%20passing-brightgreen)]() [![arch](https://img.shields.io/badge/arch-amd64%20%2B%20arm64-blue)]() [![deploy](https://img.shields.io/badge/deploy-Fly.io%20%C2%B7%20GHCR%20%C2%B7%20Vercel%20%C2%B7%20self--host-orange)]()

## What it does

Extracts real-time price feeds from M-Pesa, Airtel Money, Orange Money, and MTN MoMo aggregator APIs. Aggregates into a robust median price + volume-weighted spread per currency. **Quorum-protected** so a single-provider outage cannot move the published rate.

```
Mobile Money APIs (M-Pesa, Airtel, Orange, MTN)
    ↓
Oracle Agents (Py / Go / Sh — one per provider×country)
    ↓
Aggregation Layer (median · vol-weighted spread · quorum ≥ N providers)
    ↓
Price Feed API (FastAPI · /hunt · /feeds/all · /feeds/quorum · /feeds/stream · /metrics)
    ↓
AFRI Jetton (TON, TIP-74 · 120% over-collateralized)
```

## The five pillars

| Pillar | What it means | Where it lives |
|---|---|---|
| **Resilient** | Single-provider outage doesn't move the rate | `quorum_aggregate(min_providers=2)` · `/feeds/quorum` · polyglot ports |
| **Sovereign** | African jurisdictional + operational control | `fly.toml` jnb region · `docker-compose.yml` self-host · open-source FunC |
| **Scalable** | Edge + cloud, push + poll, multi-region | async `/feeds/all` · SSE `/feeds/stream` · multi-arch image · stateless |
| **Affordable** | Free-tier viable, $35-hardware edge | shared-cpu-1x Fly.io · POSIX shell port on Raspberry Pi · no Redis/Postgres |
| **Alternative** | Better than USDT/USDC on African settlement | mobile-money-native collateral · TON gas ~$0.005 · Telegram via TON Connect |

Full value-prop + USDT/USDC comparison: see [`SOVEREIGNTY.md`](SOVEREIGNTY.md).

## Supported providers

| Provider | Countries | Currencies | Status |
|---|---|---|---|
| Safaricom M-Pesa | KE, TZ, UG, RW, ZA, GH, CD, LS, MZ, SO | KES, TZS, UGX, RWF, ZAR, GHS, CDF, LSL, MZN, SOS | Simulated (v0.3.0) · Real API Phase-1 |
| Airtel Money | KE, UG, RW, ZA, CD, NE, GA, CG, TD | KES, UGX, RWF, ZAR, CDF, XOF, XAF | Simulated · Real API Phase-1 |
| Orange Money | CI, SN, ML, BF, NE, BJ, TG, CM, MG | XOF, XAF, MGA | Simulated · Real API Phase-1 |
| MTN MoMo | GH, UG, RW, ZA, CI, NG, CM, ZM | GHS, UGX, RWF, ZAR, XOF, NGN, XAF, ZMW | Simulated · Real API Phase-1 |

## Quick start

```sh
# Python CLI (canonical implementation)
py -3 oracle_agent.py --provider safaricom --country KE --simulate --pretty

# HTTP API
py -3 -m pip install -r requirements.txt
uvicorn api.app:app --reload
curl -s http://localhost:8000/health
curl -s -X POST http://localhost:8000/feeds/quorum \
  -H 'Content-Type: application/json' \
  -d '{"min_providers":2}'

# Tests
py -3 -m pytest tests/ -v   # 20 passing

# Self-host on any African VPS (Sovereign + Affordable)
docker compose up -d
```

## API endpoints (v0.3.0)

| Method | Path | Pillar |
|---|---|---|
| `GET` | `/health` | – |
| `GET` | `/providers` | – |
| `POST` | `/hunt` `{provider, country, simulate}` | – |
| `POST` | `/feeds/all` | Scalable (async) |
| `POST` | `/feeds/quorum` `{min_providers}` | **Resilient** |
| `GET` | `/feeds/stream?interval=N` | **Scalable** (SSE) |
| `GET` | `/metrics` | observability |

## Deploy targets

- **[Fly.io](DEPLOY.md#path-b--flyio-arm64-native-primary)** — primary, ARM64 native, `jnb` region (Johannesburg)
- **[GHCR](DEPLOY.md#path-a--ghcr-via-github-actions-recommended-zero-local-setup)** — multi-arch image (amd64 + arm64) via GitHub Actions
- **[Vercel](DEPLOY.md#path-c--vercel-serverless-python-asgi)** — serverless Python ASGI fallback
- **[Self-host](DEPLOY.md#path-e--self-host-on-african-vps-sovereign--affordable)** — any African VPS, $4–6/mo via `docker-compose.yml`

Detailed instructions: [`DEPLOY.md`](DEPLOY.md).

## Project structure

- [`oracle_agent.py`](oracle_agent.py) — canonical implementation + quorum aggregation
- [`oracle_agent.go`](oracle_agent.go) — Go port (edge performance)
- [`oracle_agent.sh`](oracle_agent.sh) — POSIX shell port (PicoClaw / Raspberry Pi edge)
- [`api/app.py`](api/app.py) — FastAPI ASGI server
- [`afri-bridge.sh`](afri-bridge.sh) — Mobile money ↔ AFRI mint/burn orchestration
- [`afri-token.fc`](afri-token.fc) — TON Jetton (TIP-74) smart contract scaffold
- [`AFRI_Blueprint.md`](AFRI_Blueprint.md) — full project blueprint + roadmap + changelog
- [`SOVEREIGNTY.md`](SOVEREIGNTY.md) — value proposition + USDT/USDC comparison
- [`EVAL_REPORT.md`](EVAL_REPORT.md) — audit + R²S² gate scores

## Roadmap

- [x] **Phase 0** — Oracle Bootstrapping (v0.3.0): provider mapping · simulated feed · quorum aggregation · async API · SSE streaming · multi-arch image · self-host path
- [ ] **Phase 1** — AFRI Jetton on TON testnet: FunC contract rewrite against TIP-74 stdlib · oracle-signed price feeds · bridge handshake
- [ ] **Phase 2** — Production rollout: provider API keys + KYC at provider boundary · liquidity onboarding (STON.fi LP) · reserve audit publication · mainnet deploy

Full roadmap: [`AFRI_Blueprint.md`](AFRI_Blueprint.md).

## Cost

- **Today (Phase 0):** free-tier viable. Fly.io shared-cpu-1x = \$0/mo. Self-host on $4–6/mo VPS.
- **Production (Phase 2, full deploy):** ~\$5K/mo for 4 providers × ~30 countries × 30 s polling, with redundancy.

## License

TBD. Open-source intent — the contract math is on-chain and auditable; the oracle is self-hostable.
