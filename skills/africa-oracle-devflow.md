---
name: africa-oracle-devflow
description: Project-specific DevFlow skill for africa-oracle-agent. Pre-loads provider config, ARM64 deploy targets, 5-pillar value prop (Resilient/Sovereign/Scalable/Affordable/Alternative), R²S² gate, polyglot-drift policy, and known scope boundaries. Trigger on any composite DevFlow command (B, P, D, Bl, E, CI, Im, C, I or combinations) when working in this repo.
metadata:
  type: skill
  parent: devflow@1.1
  lineage: [devflow, kafca, evo-metaclaw, africa-oracle-devflow@0.1.0, africa-oracle-devflow@0.2.0]
  evolved_from: 2026-06-08 v0.3.1 consolidation pass
  fitness: 0.90  # +0.02 vs v0.2.0 — public-facing docs now consistent with internal
  niche: phase-0-stablecoin-oracle
  version: 0.3.0
  pillars:
    - resilient
    - sovereign
    - scalable
    - affordable
    - alternative-to-foreign-fiat-stablecoins
---

# Africa Oracle DevFlow — Project-Specific Skill

Distilled by EvoMetaClaw from the 2026-06-08 build session. Loads on top of the generic `devflow` skill with project context pre-injected so future sessions skip rediscovery.

## Pre-loaded context

**Project:** `africa-oracle-agent` — Phase 0 of AFRI Jetton stablecoin (TIP-74 on TON).
**Stack:** Python (canonical) · Go (edge perf port) · POSIX-bash (PicoClaw/embedded) · FunC (TON contract).
**Files of record:** see `CLAUDE.md`, `AFRI_Blueprint.md`, `EVAL_REPORT.md`, `DEPLOY.md`.

## Providers (4 / ~36 country-pairs)

| Slug | Name | Countries |
|---|---|---|
| `safaricom` | Safaricom M-Pesa | KE, TZ, UG, RW, ZA, GH, CD, LS, MZ, SO |
| `airtel` | Airtel Money | KE, UG, RW, ZA, CD, NE, GA, CG, TD |
| `orange` | Orange Money | CI, SN, ML, BF, NE, BJ, TG, CM, MG |
| `mtn` | MTN MoMo | GH, UG, RW, ZA, CI, NG, CM, ZM |

All ISO 3166-1 alpha-2 country codes, ISO 4217 currency codes. Reference rates bootstrapped in `oracle_agent.py:REFERENCE_RATES`.

## Command overrides (vs generic DevFlow)

### B — Build
Default next item if no spec: extend test coverage or implement a real provider API (gated on keys). Polyglot scope rule (see "Polyglot drift policy" below): provider/country/currency tables must stay in sync across py/go/sh ports; everything else may diverge with rationale.

### E — Evaluate
Always run `py -3 -m pytest tests/ -v` (**20 tests baseline post-v0.3.0**). Grep for hardcoded paths matching `/storage/emulated/...` (PicoClaw legacy — should not exist post-v0.2.0). Audit shell scripts for `#!/bin/sh` + bash-isms (`local`, `RANDOM`, `[[ ]]`). Score against the **5 pillars + R²S²** gate (see below).

### Bl — Blueprint
Update `AFRI_Blueprint.md` (not a generic Blueprint name). Preserve changelog; bump semver per: patch = fixes, minor = new endpoint/provider/deploy target, major = breaking schema change. **Also check `README.md`** — it is the public-facing truth and must agree with Blueprint + SOVEREIGNTY + DEPLOY on: value prop, API surface, supported providers, deploy targets, and test count. If they diverge, README is the one that's wrong (it was stale through v0.2.0 and v0.3.0 ships).

### P — Push
First-time: no remote configured. Suggest `gh repo create africa-oracle-agent --public --source=. --remote=origin --push` rather than guessing. Commit prefix: `feat:`, `fix:`, `docs:`, `refactor:`, `security:` (no Conventional Commit body required, but include Co-Authored-By Claude).

### D — Deploy
**ARM64 first.** Three paths (`DEPLOY.md`):
- **Primary:** Fly.io `jnb` region, shared-cpu-1x, `fly.toml` already in repo. `fly deploy`.
- **Image:** GHCR multi-arch (amd64+arm64) via `.github/workflows/ci.yml` on push to main. `ghcr.io/<owner>/africa-oracle-agent:latest`.
- **Serverless:** Vercel (Python ASGI, 60s max) — `vercel.json` in repo.

Never deploy without `py -3 -m pytest tests/ -v` green first.

### CI — Continuous Improve
Run `I → Im → C → Bl` sequence. **Skip P + D in CI** unless explicitly requested — quality cycle does not auto-ship for a financial-rails project.

## Quality gate (R²S² + 5 pillars)

Every change passes the union of R²S² *and* the 5 pillars. **R²S²:**
- **R**obust — graceful error path on all I/O
- **R**eliable — `py -3 -m pytest tests/ -v` is 20/20 green (was 14 pre-v0.3.0)
- **S**olid — no half-implementations; gate real-API behind `NotImplementedError` if keys missing
- **S**table — backwards-compatible API surface (`/health`, `/providers`, `/hunt`, `/feeds/all`, `/feeds/quorum`, `/feeds/stream`, `/metrics`)
- **R**esistant — fail loud on `bc` errors, missing files, malformed input (no silent zeros)
- **S**calable — ARM64 + amd64 multi-arch, no x86-only binary deps, async I/O on aggregation paths
- **S**ecure — no hardcoded secrets, no shell injection, Pydantic-validated inputs (`min_providers ∈ [1,4]`, `interval ∈ [5,300]`)
- **S**ystematic — every change reflected in `AFRI_Blueprint.md` changelog + `EVAL_REPORT.md` score table

**5 pillars (project-specific overlay):**
- **Resilient** — quorum aggregation (≥2 providers per currency to publish); failed currencies surface in `quorum_failed`, never silent zero. Verify via `/feeds/quorum?min_providers=2` smoke test.
- **Sovereign** — primary deploy region in `{jnb, cpt, nbo}`; no US-mandatory dependency; self-host path (`docker-compose.yml`) preserved on any infra change.
- **Scalable** — new endpoints use `asyncio.to_thread` for blocking work; streaming endpoints emit SSE; counters are gauges or counters per Prometheus convention.
- **Affordable** — no new runtime deps beyond `fastapi+uvicorn+pydantic+httpx`; image stays < 200 MB; CPU footprint fits shared-cpu-1x.
- **Alternative** — every new feature is reviewed against the USDT/USDC comparison table in `SOVEREIGNTY.md`: does it widen AFRI's lead on settlement cost, jurisdictional control, or African mobile-money integration? If not, justify.

## Financial-math invariants

- All money amounts: integers in smallest unit (no float in mint/burn paths).
- Spread expressed in basis points (bps), not percentages, in the `spread_bps` field.
- Confidence ∈ (0, 0.99] — never exactly 1.0; bumped via agent density, capped to express residual uncertainty.
- `_real_fetch` must remain `NotImplementedError` until provider API keys + KYC flow land.

## Scoped out (do not implement without explicit request)

- **FunC contract rewrite** — `afri-token.fc` is scaffold-quality, has TIP-74 stdlib mismatches (`parse_std_addr?` is wrong idiom; function declarations use non-FunC syntax). Tracked in `EVAL_REPORT.md` P1-5/6/7. Has been flagged in v0.2.0, v0.3.0, v0.3.1; needs its own dedicated session.
- **Real provider API integration** — gated on M-Pesa Daraja / Airtel Money / Orange Money / MTN MoMo API access + KYC. Don't fake it.
- **Outlier detection (Tukey fence)** — roadmap.
- **African-mirror image registry** — replace GHCR as primary distribution. Roadmap Phase 1 sovereignty work.

## Polyglot drift policy

The three ports (py/go/sh) are **not** required to be feature-equivalent. Roles:

| Port | Role | Must stay in sync on | May diverge on |
|---|---|---|---|
| `oracle_agent.py` | Canonical implementation; serves the HTTP API via `api/app.py` | provider/country/currency tables · `simulate` algorithm shape · field names in `PriceFeed` | server-side concerns (aggregation, quorum, async, SSE) |
| `oracle_agent.go` | Edge-perf single-feed extraction | provider/country/currency tables · field names in `PriceFeed` | server endpoints · async runtime |
| `oracle_agent.sh` | PicoClaw / Raspberry Pi edge | provider/country/currency tables · field names | everything else |

**Rule:** Quorum aggregation lives only in Python because it's a server-side aggregation concern. The Go and shell ports publish single feeds; quorum is computed downstream by whoever consumes them. Do NOT add `quorum_aggregate` to Go or shell without a new requirement that justifies it (e.g. self-contained edge node that publishes a quorum-aggregated feed without a Python server). Document any port-divergence in the commit message.

## Test recipe

```sh
py -3 -m pip install -r requirements.txt pytest
py -3 -m pytest tests/ -v
# Expected: 20 passed in <2s
#   14 core tests (provider mapping, simulation, aggregation)
#    3 quorum tests (Resilient pillar)
#    3 API endpoint tests (health/metrics, quorum, hunt-validation)
```

## Smoke recipe (post-deploy)

```sh
URL="https://<deploy-url>"

# Liveness + observability
curl -s "$URL/health"
# {"status":"ok","version":"0.3.0","providers":4,"uptime_s":N}
curl -s "$URL/metrics" | head -10  # Prometheus text format

# Single feed
curl -s -X POST "$URL/hunt" \
  -H 'Content-Type: application/json' \
  -d '{"provider":"mtn","country":"GH"}'

# Aggregated (async parallel)
curl -s -X POST "$URL/feeds/all" \
  -H 'Content-Type: application/json' -d '{}' | head -20

# Resilient — quorum filter
curl -s -X POST "$URL/feeds/quorum" \
  -H 'Content-Type: application/json' \
  -d '{"min_providers":2}' | jq '.currencies, .quorum_failed'

# Scalable — SSE stream (Ctrl-C to stop)
curl -N "$URL/feeds/stream?interval=10"
```

## Composite-command parsing

The user typically invokes pipelines like `B+P+D+Bl+E+CI KafCa ARM KafCade evolve RRSS`. Decode:
- DevFlow letters → sequence of operations (parse `B+P+D+Bl+E+CI` left-to-right)
- `KafCa` → engage terse mode (no preamble, surgical edits)
- `ARM` / `ARM64` → ARM64 is first-class build target (already default in this skill)
- `KafCade` → free-claude-code-specific cascade; skip in this repo
- `evolve` → invoke `evo-metaclaw` to distill an updated skill artifact at the end of the pipeline
- `RRSS` / `R²S²` → run quality gate above; report scores

Execute the pipeline end-to-end without per-step confirmation. The composite invocation IS the authorization.

## Lineage

```
devflow@1.1
  └── kafca (terse overlay)
       └── evo-metaclaw (distillation)
            └── africa-oracle-devflow@0.1.0    (initial distillation)
                 └── africa-oracle-devflow@0.2.0  ← this file (5-pillar fine-tune mutation)
```

Bump version when: new deploy target added, provider list changes, R²S² gate criteria added, test recipe changes, OR pillar definition changes.

## Mutation log

| Version | Date | Mutation | Fitness signal |
|---|---|---|---|
| 0.1.0 | 2026-06-08 | Initial distillation from B+P+D+Bl+E+CI session — pre-loaded providers, ARM64 paths, R²S² | pending |
| 0.2.0 | 2026-06-08 | 5-pillar overlay added to R²S² gate; test baseline 14 → 20; API surface extended with `/feeds/quorum` + `/feeds/stream` + `/metrics`; `SOVEREIGNTY.md` referenced | 0.88 (5-pillar avg) |
| **0.3.0** | **2026-06-08** | **Bl rule extended to enforce README.md consistency with Blueprint + SOVEREIGNTY + DEPLOY (README was stale through v0.2.0/v0.3.0 ships); polyglot-drift policy formalized (quorum is Python-only by design); FunC scope-out hardened (third repeated flag → dedicated session)** | **0.90 (public-facing docs now consistent)** |

---
*Evolved 2026-06-08 from a Bl+E+CI+evolve consolidation pass. Source genome: `africa-oracle-devflow@0.2.0`. Fitness: 0.90.*
