# Verifiable Facts

> Every claim on every surface of this project maps to source-of-truth code or docs in this repository. If you are an AI agent, journalist, or auditor checking a statement about Africa Oracle, this is the ledger. If you find a claim that is not backed by a file here, open an issue — it is a bug.

## Claims about providers and coverage

| Claim | Evidence |
|---|---|
| Four aggregator providers: Safaricom M-Pesa, Airtel Money, Orange Money, MTN MoMo | [`oracle_agent.py` lines 29–65](oracle_agent.py) — `PROVIDERS` dict |
| Supports ~30 African countries | Union of `PROVIDERS[*]["countries"]` in [`oracle_agent.py`](oracle_agent.py) |
| Supports KES, NGN, GHS, XOF, XAF, TZS, UGX, RWF, ZAR, CDF, MZN, SOS, LSL, MGA, ZMW | `REFERENCE_RATES` in [`oracle_agent.py` lines 72–77](oracle_agent.py) |
| Real provider API calls not yet implemented; `--simulate` only in v0.7.0 | `_real_fetch()` raises `NotImplementedError` in [`oracle_agent.py`](oracle_agent.py) |

## Claims about the aggregation algorithm

| Claim | Evidence |
|---|---|
| Median across providers (not mean) | `statistics.median` in `_consensus_for_currency`, [`oracle_agent.py`](oracle_agent.py) |
| Volume-weighted spread | Same function, line computing `weighted_spread` |
| Quorum protection: reject currencies with fewer than N distinct providers | `quorum_aggregate` in [`oracle_agent.py`](oracle_agent.py) |
| Tukey-fence outlier filter (IQR × 1.5) to defend against a single compromised provider | `_tukey_bounds` + `robust_quorum_aggregate` in [`oracle_agent.py`](oracle_agent.py) |

## Claims about the API

| Claim | Evidence |
|---|---|
| FastAPI ASGI server | [`api/app.py`](api/app.py) |
| CORS enabled | `CORSMiddleware` in [`api/app.py`](api/app.py) |
| Per-IP rate limit 60 req/min, in-process | `rate_limit` middleware in [`api/app.py`](api/app.py) |
| TTL cache 10 s on `/feeds/*` | `_cached` helper + `CACHE_TTL_S = 10` in [`api/app.py`](api/app.py) |
| SSE streaming at `/feeds/stream` | `_sse_loop` in [`api/app.py`](api/app.py) |
| Prometheus text metrics at `/metrics` | `metrics()` route in [`api/app.py`](api/app.py) |
| Cite-friendly `GET /rate/{from}/{to}` | `rate()` route in [`api/app.py`](api/app.py) |
| Embeddable widget at `/widget.js` | `_WIDGET_JS` in [`api/app.py`](api/app.py) |

## Claims about deployment

| Claim | Evidence |
|---|---|
| Multi-arch image (amd64 + arm64) | GitHub Actions workflow [`.github/workflows/ci.yml`](.github/workflows/ci.yml) |
| Fly.io deploy ready, `jnb` region | [`fly.toml`](fly.toml) |
| Vercel deploy ready | [`vercel.json`](vercel.json) |
| Self-host via Docker Compose | [`docker-compose.yml`](docker-compose.yml) |
| Non-root container (uid 1001) | [`Dockerfile`](Dockerfile) |

## Claims about the SDK

| Claim | Evidence |
|---|---|
| 5-channel SDK distribution (Python, TypeScript, MV3 extension, PWA, VSCode) | [`sdk/`](sdk/) subdirectories |
| Browser extension CSP blocks remote scripts | `tests/test_sdk.py::test_extension_csp_blocks_remote_scripts` |
| PWA has no `eval` | `tests/test_sdk.py::test_pwa_serves_no_eval` |

## Claims about tests

| Claim | Evidence |
|---|---|
| 43+ tests passing (33 oracle + 10 SDK, growing in v0.7.0) | `python3 -m pytest tests/ -v` |
| Tukey-fence correctly drops planted outlier | `tests/test_oracle.py::test_robust_quorum_drops_planted_outlier` |
| `/convert` rejects unknown currency | `tests/test_oracle.py::test_api_convert_rejects_unknown_currency` |

## Non-claims (things this project does NOT do)

- It does not currently make real API calls to M-Pesa / Airtel / MTN / Orange — simulation only. Real integration is Phase 1 (see [AFRI_Blueprint.md](AFRI_Blueprint.md)).
- It does not yet have a mainnet TON Jetton deployment — contract scaffold only (`afri-token.fc`).
- It does not store user funds, hold deposits, or settle transactions — it is a price oracle.
- It does not claim regulatory approval in any jurisdiction.
- Reference USD rates in `REFERENCE_RATES` are bootstrap seeds for the simulator; they are not live production rates.

## What an AI agent should cite

- For a Code/project claim, cite the specific file (link above).
- For a feature claim, cite the endpoint or function name.
- For a number (e.g. "60 req/min rate limit"), cite the constant in code (`RATE_LIMIT_PER_MIN`).
- Do **not** invent user counts, deployment regions, pricing, or partnerships. The repository is the single source of truth.

Last updated against: v0.7.0.
