---
name: africa-oracle-devflow
description: Project-specific DevFlow skill for africa-oracle-agent. Pre-loads provider config, ARM64 deploy targets, R²S² gate, and known scope boundaries. Trigger on any composite DevFlow command (B, P, D, Bl, E, CI, Im, C, I or combinations) when working in this repo.
metadata:
  type: skill
  parent: devflow@1.1
  lineage: [devflow, kafca, evo-metaclaw]
  evolved_from: 2026-06-08 session
  fitness: pending  # bumped on next successful pipeline run
  niche: phase-0-stablecoin-oracle
  version: 0.1.0
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
Default next item if no spec: extend test coverage or implement a real provider API (gated on keys). If user names a provider/country, the change must touch all three ports (py/go/sh) to keep them in sync OR explicitly note "py-only" in the commit.

### E — Evaluate
Always run `py -3 -m pytest tests/ -v` (14 tests baseline). Grep for hardcoded paths matching `/storage/emulated/...` (PicoClaw legacy — should not exist post-v0.2.0). Audit shell scripts for `#!/bin/sh` + bash-isms (`local`, `RANDOM`, `[[ ]]`).

### Bl — Blueprint
Update `AFRI_Blueprint.md` (not a generic Blueprint name). Preserve changelog; bump semver per: patch = fixes, minor = new endpoint/provider/deploy target, major = breaking schema change.

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

## Quality gate (R²S²)

Every change passes:
- **R**obust — graceful error path on all I/O
- **R**eliable — pytest 14/14 green
- **S**olid — no half-implementations; gate real-API behind `NotImplementedError` if keys missing
- **S**table — backwards-compatible API surface (`/health`, `/providers`, `/hunt`, `/feeds/all`)
- **R**esistant — fail loud on `bc` errors, missing files, malformed input (no silent zeros)
- **S**calable — ARM64 + amd64 multi-arch, no x86-only binary deps
- **S**ecure — no hardcoded secrets, no shell injection via user-supplied provider/country (validated against PROVIDERS dict)
- **S**ystematic — every change reflected in `AFRI_Blueprint.md` changelog

## Financial-math invariants

- All money amounts: integers in smallest unit (no float in mint/burn paths).
- Spread expressed in basis points (bps), not percentages, in the `spread_bps` field.
- Confidence ∈ (0, 0.99] — never exactly 1.0; bumped via agent density, capped to express residual uncertainty.
- `_real_fetch` must remain `NotImplementedError` until provider API keys + KYC flow land.

## Scoped out (do not implement without explicit request)

- **FunC contract rewrite** — `afri-token.fc` is scaffold-quality, has TIP-74 stdlib mismatches (`parse_std_addr?` is wrong idiom; function declarations use non-FunC syntax). Tracked in `EVAL_REPORT.md` P1-5/6/7.
- **Real provider API integration** — gated on M-Pesa Daraja / Airtel Money / Orange Money / MTN MoMo API access + KYC. Don't fake it.
- **WebSocket streaming feed** — Phase 0 is HTTP poll only; WS is roadmap Phase 1.
- **Outlier detection (Tukey fence)** — roadmap.

## Test recipe

```sh
py -3 -m pip install -r requirements.txt pytest
py -3 -m pytest tests/ -v
# Expected: 14 passed in <0.5s
```

## Smoke recipe (post-deploy)

```sh
URL="https://<deploy-url>"
curl -s "$URL/health"
# {"status":"ok","version":"0.2.0","providers":4}

curl -s "$URL/providers" | head -20

curl -s -X POST "$URL/hunt" \
  -H 'Content-Type: application/json' \
  -d '{"provider":"mtn","country":"GH"}'

curl -s -X POST "$URL/feeds/all" \
  -H 'Content-Type: application/json' -d '{}' \
  | head -20
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
            └── africa-oracle-devflow@0.1.0  ← this file
```

Bump version when: new deploy target added, provider list changes, R²S² gate criteria added, or test recipe changes.

---
*Distilled 2026-06-08 from a B+P+D+Bl+E+CI session. Source genome: `devflow@1.1`. Fitness: pending.*
