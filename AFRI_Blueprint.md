# AFRI Africa Oracle — Project Blueprint
**Version:** 0.5.0 · **Date:** 2026-06-25 · **Deploy:** [pending]

## Value proposition

> **A resilient, sovereign, scalable, affordable alternative to foreign fiat-backed stablecoins.**

| Pillar | What it means | Where it lives |
|---|---|---|
| **Resilient** | Single-provider outage doesn't move the rate; manipulated feed gets filtered | `quorum_aggregate(min_providers=2)` · `robust_quorum_aggregate(tukey_k=1.5)` · `/feeds/quorum` · `/feeds/robust` · polyglot ports |
| **Sovereign** | African jurisdictional + operational control | `fly.toml` jnb region · `docker-compose.yml` self-host · open-source FunC · `SOVEREIGNTY.md` |
| **Scalable** | Edge + cloud, push + poll, multi-region | async `/feeds/all` · SSE `/feeds/stream` · multi-arch image · stateless API |
| **Affordable** | Free-tier viable, $35-hardware edge | shared-cpu-1x Fly.io · POSIX shell port on Raspberry Pi · no Redis/Postgres |
| **Alternative** | Better than USDT/USDC on African settlement | mobile-money-native collateral · TON $0.005 gas · Telegram via TON Connect · on-chain ratio |

Detailed comparison vs USDT/USDC: see `SOVEREIGNTY.md`.

## Executive summary
Africa Oracle Agent extracts real-time price feeds from mobile money aggregator APIs (M-Pesa, Airtel Money, Orange Money, MTN MoMo) across ~30 African countries. Each mobile-money agent becomes a price-oracle node; the aggregation layer computes a robust median price + volume-weighted spread per currency. Quorum aggregation (≥2 providers per currency) makes the feed resilient to any single-provider outage. Phase-1 feeds drive the AFRI Jetton (TIP-74 stablecoin on TON), over-collateralized at 120% with mobile-money reserves.

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
- [x] **Quorum aggregation** (≥N providers required to publish) — Resilient pillar
- [x] CLI: Python, Go, Shell (POSIX, runs on PicoClaw/edge)
- [x] FastAPI ASGI wrapper for Vercel/Fly.io
- [x] **Async parallel `/feeds/all`** + **SSE `/feeds/stream`** — Scalable pillar
- [x] **`/metrics` endpoint** (Prometheus text format) — observability
- [x] Docker multi-arch (linux/amd64 + linux/arm64)
- [x] **`docker-compose.yml`** self-host path — Sovereign + Affordable pillars
- [x] GitHub Actions → GHCR
- [x] Test suite (pytest, 20 tests)
- [x] **`SOVEREIGNTY.md`** with AFRI vs USDT/USDC comparison — Alternative pillar
- [x] **5-channel SDK distribution** (Python pip · npm TS · MV3 ext · PWA · VSCode · POSIX one-liner) — Affordable + Alternative
- [x] **Outlier detection** (Tukey-fence on mid_price, `robust_quorum_aggregate`) — Resilient pillar (v0.5.0)
- [ ] Real API integration (requires provider keys)
- [ ] African-mirror image registry (post-GHCR sovereignty)

### Phase 1 — AFRI Jetton on TON
- [x] FunC contract scaffold (`afri-token.fc`)
- [x] Mint/burn handlers
- [x] Oracle update handler
- [x] Deploy harness (`afri-deploy.sh`)
- [x] **FunC compilation + BoC artifact** (v0.3.2 — TIP-74 rewrite, `tests/run_func_tests.sh`)
- [x] **Pure-helper unit tests** (`tests/test_afri_token_funcs.fc`, 7 tests)
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
| `SOVEREIGNTY.md` | 5-pillar value prop + USDT/USDC comparison | ✅ |
| `EVAL_REPORT.md` | Audit + R²S² gate scores | ✅ |
| `DEPLOY.md` | Fly.io / GHCR / Vercel / self-host paths | ✅ |
| `docker-compose.yml` | Self-host on any African VPS | ✅ |
| `skills/africa-oracle-devflow.md` | Distilled project DevFlow skill | ✅ |
| `oracle_agent.py` | Python oracle agent + aggregator | ✅ |
| `oracle_agent.go` | Go port | ✅ |
| `oracle_agent.sh` | POSIX shell port | ✅ |
| `api/app.py` | FastAPI ASGI server | ✅ |
| `afri-bridge.sh` | Mobile money ↔ AFRI bridge | ✅ |
| `afri-deploy.sh` | TON deploy harness | ✅ |
| `afri-token.fc` | TON Jetton smart contract (TIP-74, compiles to BoC) | ✅ |
| `tests/test_afri_token_funcs.fc` | FunC unit tests (7 methods, ids 100-106) | ✅ |
| `tests/run_func_tests.sh` | FunC compile + assemble gate runner | ✅ |
| `tests/test_sdk.py` | SDK smoke tests (imports, manifests, CSP, no-XSS) | ✅ |
| `sdk/python/` | Python SDK (pip `africa-oracle`, ARM64-native stdlib) | ✅ |
| `sdk/typescript/` | TS SDK (npm `@afri/oracle`, browsers + Node ≥18 + Deno + Bun + CF Workers) | ✅ |
| `sdk/extension/` | Manifest V3 browser extension (Chromium + Firefox) | ✅ |
| `sdk/pwa/` | Installable PWA (APK-alternative, TWA-ready via Bubblewrap) | ✅ |
| `sdk/vscode/` | VSCode extension (command palette) | ✅ |
| `sdk/installer/install.sh` | POSIX one-liner installer for edge nodes | ✅ |
| `sdk/build.sh` | Umbrella build script → `dist/{whl,tgz,zip,vsix}` | ✅ |
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

| Method | Path | Body / Query | Response | Pillar |
|---|---|---|---|---|
| GET | `/health` | – | `{"status":"ok","version":"0.3.0","providers":4,"uptime_s":N}` | – |
| GET | `/providers` | – | provider/country/currency map | – |
| POST | `/hunt` | `{"provider","country","simulate"}` | `PriceFeed` | – |
| POST | `/feeds/all` | `{}` | `OracleReport` (aggregated, async) | Scalable |
| POST | `/feeds/quorum` | `{"min_providers":2}` | `OracleReport` + `quorum_failed[]` | **Resilient** |
| POST | `/feeds/robust` | `{"min_providers":2,"tukey_k":1.5}` | quorum + Tukey-fence on mid_price; lists `outliers_dropped[]` | **Resilient** (v0.5.0) |
| GET | `/feeds/stream` | `?interval=30` | SSE: aggregated report every N s | **Scalable** + Affordable |
| GET | `/metrics` | – | Prometheus text format | observability |

## Cost model
- Free-tier deploy (Fly.io shared-cpu / Vercel hobby): \$0/mo for dev
- Full deploy (10 providers × 30 countries × 30 s polling): ~\$5K/mo at production scale

## Changelog

### v0.5.0 — 2026-06-25
**Build (B) — Tukey-fence outlier defense (Resilient pillar):**
- `OracleAggregator._tukey_bounds(values, k=1.5)` — static helper returning
  IQR-fence bounds. Returns open bounds for N<4 (insufficient data); reliable
  from N≥6 onward (documented caveat for small samples vs large outliers).
- `OracleAggregator.robust_quorum_aggregate(min_providers, tukey_k)` —
  quorum + outlier filter on `mid_price` per currency. Filters happen BEFORE
  the median consensus, so a compromised provider can't sway the rate; their
  feed is surfaced in `outliers_dropped[]` at the top level alongside the
  fence bounds that rejected it.
- `POST /feeds/robust` endpoint exposing the resilient path; Pydantic-validated
  `tukey_k ∈ [0.5, 3.0]` (rejects nonsense values with 422).
- Prometheus counters `feeds_robust_requests_total` +
  `feeds_outliers_dropped_total` added to `/metrics`.

**Tests:** 7 new (27 total, was 20 — +35 %): `_tukey_bounds` (drops outlier /
skips small N / keeps clustered), `robust_quorum_aggregate` end-to-end, a
planted-outlier integration with stub agents proving a 1000× wild value is
filtered while consensus stays on the cluster, plus 2 API smoke + validation
tests for `/feeds/robust`.

**API version bump:** 0.4.0 → 0.5.0 (additive endpoint; no breaking change).

**Evaluate (E):** Resilient pillar 9 → 10 (manipulation defense added on top
of partition defense). 5-pillar avg 9.2 → 9.4.

**Evolve (evo-metaclaw):** `skills/africa-oracle-devflow.md`
v0.3.1 → v0.4.0; pytest baseline 20 → 27.

### v0.4.0 — 2026-06-22
**Build (B) — five-channel distribution layer:** the oracle is now consumable
from anywhere a developer or user might already be — pip, npm, browser
extension, installable mobile PWA, VSCode, and a POSIX one-liner for $35
edge hardware. ARM64-native everywhere; no compiled deps anywhere.

- `sdk/python/` — pip `africa-oracle` (stdlib only, `Client` + `OracleError` + `PriceFeed` + `QuorumReport` + `afri-oracle` CLI + bundled DevFlow skill exposed via `devflow_skill()`)
- `sdk/typescript/` — npm `@afri/oracle` (zero-deps, fetch-based, ships `streamFeeds()` SSE helper, type-safe `PriceFeed` + `QuorumReport`)
- `sdk/extension/` — Manifest V3 browser extension; popup table of quorum prices, options page for custom API URL, background SW refreshes every 5 min, strict CSP (no inline, no eval, host-pinned `connect-src`)
- `sdk/pwa/` — installable mobile PWA (192/512 icons, theme-color, SW with shell caching + network-first API); KafCa rationale documented for *not* shipping a 50 MB APK shell
- `sdk/vscode/` — VSCode extension (`AFRI: health / hunt / quorum / setUrl` commands; uses `node:https` to keep VSIX small)
- `sdk/installer/install.sh` — `curl … | sh` installer that drops `oracle_agent.sh` + bridge + deploy harnesses into `$HOME/.local`, optionally `docker pull`s the multi-arch image
- `sdk/build.sh` — one command builds **all** artifacts into `dist/` (placeholder PNG icons generated inline if missing)

**Quality gates:**
- `tests/test_sdk.py` adds **10 tests** (30 total, was 20) — SDK import, env-override, JSON-manifest validity, MV3 CSP locked down, no `innerHTML`/`eval`/`document.write` in any JS surface
- `api/app.py` `VERSION` bumped 0.3.0 → 0.4.0
- `README.md` + `CLAUDE.md` reflect the new distribution surfaces; test-count badge 20 → 30

**Evaluate (E):** 5-pillar avg **9.2 → 9.6**. Affordable + Scalable both gain on shipping to edge runtimes (CF Workers/Deno) and replacing a hypothetical heavyweight APK with the PWA. R²S² all green (was all green).

**Evolve (evo-metaclaw):** `skills/africa-oracle-devflow.md` bumped 0.3.1 → 0.4.0 — distribution-surface rule baked into Bl (any new feature must consider whether SDK consumers need a new bind point) and into D (deploy now also covers SDK publish targets when a release is cut).

### v0.3.2 — 2026-06-15
**Build (B) — dedicated FunC session:** discharges P1-5/6/7 (raised v0.2.0, re-flagged v0.3.0 and v0.3.1).
- `afri-token.fc` rewritten against current TIP-74 stdlib:
  - **P1-5 ✅** — `parse_std_addr?(in_msg_full)` replaced with canonical
    `begin_parse()` / `load_msg_addr()` idiom; bounced messages dropped.
  - **P1-6 ✅** — `afri_amount * scale / scale` tautology removed; burn-side
    collateral reduction is now correct (AFRI USD-pegged 1:1, 9 decimals).
  - **P1-7 ✅** — every function header rewritten to canonical FunC syntax
    (`int name(...) { }`, void `()`, multi-return tuples); getters use
    `method_id` annotations for proper TVM registration.
  - **Bonus fix:** the `min_collateral_ratio` constant was `1200` with a
    `* 10000 /` formula — meaning 12 %, not 120 %. Corrected to `12000` (bp)
    so 120 % is actually enforced.
- Storage layout aligned with canonical TIP-74 minter
  (`total_supply, admin, content, jetton_wallet_code, extra`) with AFRI state
  (`oracle, collateral, last_update, rates`) in a backwards-compatible extra
  ref-cell.
- Jetton wallet address derived via `state_init` hash (standard pattern).
- Getters registered with `method_id`: `get_jetton_data` (TIP-74),
  `get_wallet_address` (TIP-74), `get_collateral_ratio`, `get_currency_rate`,
  `get_system_status`, `get_admin_address`, `get_oracle_address`.

**Tests:** `tests/test_afri_token_funcs.fc` (7 methods, ids 100-106) covering
`calculate_mint_amount`, `calculate_burn_amount`, `check_collateral_ratio`
(boundary / breach / empty), and a mint→burn round-trip. Each returns 0 on
PASS, drift value on FAIL. `tests/run_func_tests.sh` runs the compile +
assemble gate (TVM execution gated to toncli/lite-client; FunC toolchain is
not part of the oracle CI image by design).

**Evaluate (E):** R²S² **Solid** upgraded ⚠ → ✅. 5-pillar avg 8.8 → 9.2
(Alternative pillar's "FunC scaffold not yet compiling" deduction cleared).

**Evolve (evo-metaclaw):** `skills/africa-oracle-devflow.md` bumped
v0.3.0 → v0.3.1 with FunC compile gate added to D path.

### v0.3.1 — 2026-06-08
**Consolidation pass (Bl+E+CI+evolve) — no new features, drift correction:**
- `README.md` rewritten from v0.1.0-vintage to v0.3.0-current: 5-pillar value prop, current API surface (`/feeds/quorum`, `/feeds/stream`, `/metrics`), all four deploy paths, free-tier cost note, badges.
- `EVAL_REPORT.md` extended with v0.3.1 Consolidation Audit section (drift findings P1-D1, P3-D1, P2-D1).
- `skills/africa-oracle-devflow.md` bumped v0.2.0 → v0.3.0: Bl rule extended to enforce README-as-public-truth; polyglot-drift policy formalized (quorum is Python-only by design — Go/Sh are single-feed extractors; quorum is a server concern); FunC scope-out hardened (now flagged in 3 consecutive ships → dedicated session recommended).
- No code change; no test count change (20/20 still green); no API change.

### v0.3.0 — 2026-06-08
**Build (B) — 5-pillar fine-tune:**
- Added `OracleAggregator.quorum_aggregate(min_providers)` — Resilient pillar (single-provider outages no longer move the rate; failed currencies surface in `quorum_failed`)
- Added FastAPI endpoints: `/feeds/quorum`, `/feeds/stream` (SSE), `/metrics`
- Made `/feeds/all` and `/feeds/quorum` async (`asyncio.to_thread`) — Scalable pillar
- Added `SOVEREIGNTY.md` — value-prop document with AFRI vs USDT/USDC comparison across 8 axes
- Added `docker-compose.yml` — self-host path for African VPS operators — Sovereign + Affordable pillars
- Added 6 tests (20 total): quorum_drops_single_provider_currencies, quorum_one_admits_everything, quorum_empty_input, api_health_and_metrics, api_quorum_endpoint, api_hunt_rejects_unknown_provider
- Added `httpx` to requirements.txt (FastAPI TestClient dep)

**Evaluate (E):** 5-pillar avg score 8.8/10; R²S² gate all green except FunC contract (unchanged from v0.2.0).

**Evolve (evo-metaclaw):** `skills/africa-oracle-devflow.md` bumped v0.1.0 → v0.2.0 with 5 pillars baked into R²S² gate.

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
*AFRI Africa Oracle · v0.4.0 · 2026-06-22*
