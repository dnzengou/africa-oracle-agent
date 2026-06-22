# CLAUDE.md — Africa Oracle Extraction Agent

Project context for AI coding assistants.

## What this is
Phase 0 of African stablecoin (AFRI Jetton on TON). Three reference implementations of the same oracle agent:
- `oracle_agent.py` — Python CLI + simulator (canonical)
- `oracle_agent.go` — Go CLI port
- `oracle_agent.sh` — POSIX shell port (for edge/embedded/PicoClaw)

Plus bridge layer:
- `afri-bridge.sh` — Mobile money ↔ AFRI mint/burn orchestration
- `afri-token.fc` — TON Jetton (TIP-74) smart contract
- `afri-deploy.sh` — TON testnet/mainnet deploy harness

Plus distribution layer (v0.4.0):
- `sdk/python/` — pip-installable Python SDK (stdlib only, ARM64-native)
- `sdk/typescript/` — npm `@afri/oracle` for browser/Node/Deno/Bun/CF Workers
- `sdk/extension/` — Manifest V3 browser extension (Chromium + Firefox)
- `sdk/pwa/` — installable mobile PWA (TWA-ready, APK-alternative)
- `sdk/vscode/` — VSCode extension (command palette)
- `sdk/installer/install.sh` — one-liner POSIX installer for edge nodes
- `sdk/build.sh` — builds all artifacts into `dist/`

## How to run

```sh
# Python (primary)
python3 oracle_agent.py --provider safaricom --country KE --simulate --pretty
python3 oracle_agent.py --all --interval 30 --output feeds.jsonl

# FastAPI server (for Vercel/Fly.io)
uvicorn api.app:app --reload
curl http://localhost:8000/health
curl -X POST http://localhost:8000/hunt -d '{"provider":"safaricom","country":"KE"}' -H 'Content-Type: application/json'

# Docker (ARM64 + AMD64)
docker buildx build --platform linux/amd64,linux/arm64 -t africa-oracle:latest .
docker run --rm africa-oracle:latest --provider mtn --country GH --pretty

# Tests
pytest tests/ -v       # 30 passing (20 core + 10 SDK)

# Build all distribution artifacts
bash sdk/build.sh      # → dist/{whl,tgz,zip,vsix}
```

## Conventions
- All money amounts: integers in smallest unit (no float in financial paths)
- Reference rates in `REFERENCE_RATES` are bootstrapped — production reads live API
- Simulation mode is the default; `--simulate=False` requires real API keys (not yet implemented)
- Currency codes: ISO 4217 (KES, NGN, XOF, XAF, etc.)
- Country codes: ISO 3166-1 alpha-2 (KE, NG, CI, etc.)

## Deploy targets
- **Fly.io** — primary, ARM64 native (`fly.toml`)
- **GHCR** — multi-arch image via GitHub Actions (`.github/workflows/ci.yml`)
- **Vercel** — Python ASGI serverless (`vercel.json`)

## Quality gates (R²S²)
Every change must be Robust, Reliable, Solid, Stable, Resistant, Scalable, Secure, Systematic.
- No hardcoded API keys / secrets
- All external I/O has timeout + error handling
- Financial math: integers in smallest unit, no float
- Tests cover currency/country edge cases
