# AFRI Africa Oracle — Project Blueprint
**Version:** 0.2.0 · **Date:** 2026-06-08 · **Deploy:** [pending]

## Executive summary
Africa Oracle Agent extracts real-time price feeds from mobile money aggregator APIs (M-Pesa, Airtel Money, Orange Money, MTN MoMo) across ~30 African countries. Each mobile-money agent becomes a price-oracle node; the aggregation layer computes a robust median price + volume-weighted spread per currency. Phase-1 feeds drive the AFRI Jetton (TIP-74 stablecoin on TON), over-collateralized at 120% with mobile-money reserves.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ Mobile Money APIs (M-Pesa, Airtel, Orange, MTN)                 │
└──────────────────────────────┬──────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│ Oracle Extraction Agents (Py / Go / Sh; one per provider×country)│
│   - poll APIs every 30s                                          │
│   - simulate mode for dev (default)                              │
└──────────────────────────────┬──────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│ Aggregation Layer (median price, vol-weighted spread, confidence) │
└──────────────────────────────┬──────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│ Price Feed API (FastAPI ASGI · /health · /hunt · /feeds)         │
└──────────────────────────────┬──────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│ AFRI Bridge (afri-bridge.sh) → afri-token.fc (TON Jetton)         │
│   mint: momo deposit + ref → verify → mint AFRI                  │
│   burn: burn AFRI → momo payout                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Roadmap

### Phase 0 — Oracle Bootstrapping  (current)
- [x] Provider/country/currency mapping (4 providers × ~30 countries)
- [x] Simulated price feed (realistic spreads, time-of-day volume)
- [x] Aggregation: median price + vol-weighted spread
- [x] CLI: Python, Go, Shell (POSIX, runs on PicoClaw/edge)
- [x] FastAPI ASGI wrapper for Vercel/Fly.io
- [x] Docker multi-arch (linux/amd64 + linux/arm64)
- [x] GitHub Actions → GHCR
- [x] Test suite (pytest)
- [ ] Real API integration (requires provider keys)
- [ ] WebSocket streaming feed
- [ ] Outlier detection (Tukey fence on spread)

### Phase 1 — AFRI Jetton on TON
- [x] FunC contract scaffold (`afri-token.fc`)
- [x] Mint/burn handlers
- [x] Oracle update handler
- [x] Deploy harness (`afri-deploy.sh`)
- [ ] FunC compilation + BoC artifact
- [ ] Testnet deployment + verify
- [ ] Bridge ↔ oracle handshake (signed price feeds)
- [ ] Front-running protection (commit-reveal mint)

### Phase 2 — Production rollout
- [ ] Provider API keys + KYC flow
- [ ] Liquidity onboarding (LP pool on STON.fi)
- [ ] Reserve audit publication
- [ ] Mainnet deploy

## Module / File manifest

| File | Purpose | Status |
|------|---------|--------|
| `README.md` | Public overview | ✅ |
| `CLAUDE.md` | AI-assistant context | ✅ |
| `AFRI_Blueprint.md` | This file | ✅ |
| `oracle_agent.py` | Python oracle agent + aggregator | ✅ |
| `oracle_agent.go` | Go port | ✅ |
| `oracle_agent.sh` | POSIX shell port | ✅ |
| `api/app.py` | FastAPI ASGI server | ✅ |
| `afri-bridge.sh` | Mobile money ↔ AFRI bridge | ✅ |
| `afri-deploy.sh` | TON deploy harness | ✅ |
| `afri-token.fc` | TON Jetton smart contract | ✅ |
| `Dockerfile` | Multi-arch image | ✅ |
| `fly.toml` | Fly.io ARM64 config | ✅ |
| `vercel.json` | Vercel ASGI config | ✅ |
| `requirements.txt` | Python deps | ✅ |
| `.github/workflows/ci.yml` | CI → GHCR | ✅ |
| `tests/test_oracle.py` | Unit tests | ✅ |
| `.gitignore` | Git excludes | ✅ |

## Supported providers

| Provider | Countries | Currencies | Agents (approx) |
|---|---|---|---|
| Safaricom M-Pesa | KE, TZ, UG, RW, ZA, GH, CD, LS, MZ, SO | KES, TZS, UGX, RWF, ZAR, GHS, CDF, LSL, MZN, SOS | 15 000 |
| Airtel Money | KE, UG, RW, ZA, CD, NE, GA, CG, TD | KES, UGX, RWF, ZAR, CDF, XOF, XAF | 8 000 |
| Orange Money | CI, SN, ML, BF, NE, BJ, TG, CM, MG | XOF, XAF, MGA | 12 000 |
| MTN MoMo | GH, UG, RW, ZA, CI, NG, CM, ZM | GHS, UGX, RWF, ZAR, XOF, NGN, XAF, ZMW | 10 000 |

## Deploy matrix

| Target | Trigger | Image | Notes |
|---|---|---|---|
| Fly.io | `fly deploy` | from Dockerfile | ARM64 native, primary |
| GHCR | push to main | `ghcr.io/<owner>/africa-oracle-agent:latest` | multi-arch (amd64+arm64) via Actions |
| Vercel | git push (auto) | serverless Python ASGI | 60 s max; free tier OK for /health + /hunt |

## API surface (`api/app.py`)

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/health` | – | `{"status":"ok","version":"0.2.0"}` |
| POST | `/hunt` | `{"provider","country","simulate"}` | `PriceFeed` |
| POST | `/feeds/all` | `{}` | `OracleReport` (aggregated) |
| GET | `/providers` | – | provider list |

## Cost model
- Free-tier deploy (Fly.io shared-cpu / Vercel hobby): \$0/mo for dev
- Full deploy (10 providers × 30 countries × 30 s polling): ~\$5K/mo at production scale

## Changelog

### v0.2.0 — 2026-06-08
**Build (B):**
- Added FastAPI ASGI wrapper (`api/app.py`) for serverless / container deploy
- Added Dockerfile (multi-arch `linux/amd64 + linux/arm64`)
- Added Fly.io config (`fly.toml`) for ARM64-native deploy in `jnb` region
- Added GitHub Actions → GHCR multi-arch publish (`.github/workflows/ci.yml`)
- Added Vercel config (`vercel.json`) for Python serverless
- Added pytest test suite (`tests/test_oracle.py`, 14 tests)
- Added `CLAUDE.md` (AI context) and `AFRI_Blueprint.md` (this file)
- Added `.gitignore` and `requirements.txt`

**Evaluate (E):**
- Produced `EVAL_REPORT.md` — 4 P0/P1 fixes identified, scored 7.25/10 avg

**Improve (Im):**
- `oracle_agent.py`: nanosecond+nonce agent_id (no second-resolution collisions)
- `oracle_agent.py`: true statistics.median (not upper-mid for even lists)
- `oracle_agent.py`: O(1) provider_slug via stored attribute (was O(n) index lookup)
- `oracle_agent.go`: removed deprecated `rand.Seed` call
- `afri-bridge.sh`: relative `BASE_DIR` (was Android-only `/storage/emulated/...`)
- `afri-bridge.sh`: `#!/usr/bin/env bash` (was sh, but used bash-isms)
- `afri-bridge.sh`: `bcq` helper — bc errors no longer swallowed to silent zero
- `afri-deploy.sh`: relative `CONTRACT_DIR`; `FUNC_STDLIB` overridable via env

### v0.1.0 — 2026-06-07
- Initial release: oracle agent in Py/Go/Sh
- Provider/country/currency mapping
- Simulated price feed with realistic spreads
- AFRI Jetton FunC contract scaffold
- Bridge + deploy shell harnesses

---
*AFRI Africa Oracle · v0.2.0 · 2026-06-08*
