# Evaluation Report — Africa Oracle Agent — 2026-06-08

## Security  (P0)

- **P0-1 — `afri-bridge.sh:17`** — `BASE_DIR="/storage/emulated/0/Download/picoclaw/workspace/africa-oracle-agent"` hardcoded Android (PicoClaw) path. Will fail silently on every other platform (Fly.io container, Linux server, CI runner) → script falls through to fallback rates. Same issue at `afri-deploy.sh:18`. **Fix:** `BASE_DIR="$(cd "$(dirname "$0")" && pwd)"`.
- **P0-2 — `afri-bridge.sh:161` / `:240`** — `bc` errors swallowed: `... || echo "0"`. A failed conversion produces \$0 mint or 0-AFRI burn silently. **Fix:** fail the operation explicitly when `bc` returns non-zero or empty.
- ✅ No hardcoded API keys, no `eval`, no `innerHTML`, no `document.write`, no shell injection in known-good inputs.

## Correctness  (P1)

- **P1-1 — `oracle_agent.py:91-93`** — `agent_id` uses `int(time.time())` (second resolution). Two `OracleAgent(p,c)` calls within the same second produce identical `agent_id`. **Fix:** `time.time_ns()` or append `os.urandom(4).hex()`.
- **P1-2 — `oracle_agent.py:205-206`** — `median` via `prices[len(prices)//2]` returns upper-mid for even-length lists, not the true median. Go port (`oracle_agent.go:175-185`) does this correctly. **Fix:** use `statistics.median(...)` or mirror Go's branch.
- **P1-3 — `afri-bridge.sh:86`** — `[ "$africa_hour" -ge 22 ] || [ "$africa_hour" -le 5 ] && vol_mult=0.3` — precedence ambiguity in POSIX; the `&&` may bind only to the second clause depending on shell. **Fix:** parenthesise with `{ ... ; }` or split into `if`.
- **P1-4 — `afri-bridge.sh:37,62,117…`** — `local` keyword + `RANDOM`/`local`/arithmetic `$(( ... ))` are bash-isms, but script uses `#!/bin/sh`. Will break on `dash`/`busybox-ash`. **Fix:** change shebang to `#!/bin/bash` or strip bash-isms.
- **P1-5 — `afri-token.fc:132,211`** — `parse_std_addr?(in_msg_full)` is not in TIP-74 stdlib; correct idiom is `cs = in_msg_full.begin_parse(); sender = cs~load_msg_addr();`. Will fail FunC compile.
- **P1-6 — `afri-token.fc:188`** — `int payout_usd = afri_amount * scale / scale;` is a tautology (== `afri_amount`). Dead arithmetic, likely placeholder.
- **P1-7 — `afri-token.fc:78,93,…`** — function declarations `() name(...) returns int` use non-FunC syntax; should be `int name(int x, int y) { ... }`.

## Performance  (P2)

- **P2-1 — `oracle_agent.py:238`** — aggregator returns `raw_feeds` (every per-agent dict) by default. At full scale (10 providers × 30 countries = 300 feeds × 30 s polling), this triples payload size. README/comment acknowledges this. **Fix:** strip `raw_feeds` unless `--verbose` is set.
- **P2-2 — `oracle_agent.sh:55-120`** — each `simulate_price` call shells out to `bc` ~10×. For `--all` (≥17 calls), that's >170 `bc` processes per cycle. **Fix:** use `awk` for arithmetic in one shot, or accept this is shell-port territory.
- **P2-3 — `oracle_agent.go:295`** — `rand.Seed(...)` deprecated since Go 1.20; not a perf issue but emits warning. **Fix:** drop the call (auto-seeded since 1.20) or use `math/rand/v2`.

## Quality / Consistency  (P3–P4)

- **P3-1** — Three implementations (py/go/sh) duplicate provider config tables. Drift risk: Go has `Currency` key for `SO` missing in Safaricom (compare `oracle_agent.go:35` vs `oracle_agent.py:33`)?  Actually checked — both have it. Still: extract to a shared `providers.json` and codegen the three.
- **P3-2** — `oracle_agent.sh` `--all` enumerates a hand-edited subset of provider×country pairs (17 of ~36). Inconsistent with py/go which enumerate all.
- **P3-3** — No type hints on `OracleAggregator.aggregate()` return value (`-> dict`). Pydantic model would tighten the contract with the FastAPI layer.
- **P4-1** — `oracle_agent.py:133` — `list(PROVIDERS.values()).index(self.provider)` is O(n) and brittle (dict.values() is not guaranteed identity-equal). Replace with a stored `self.slug` from `__init__`.

## Score

| Axis | Score | Notes |
|---|---|---|
| Security | 8 / 10 | Hardcoded Android paths in shell scripts; otherwise clean |
| Correctness | 6 / 10 | Median bug, agent_id collision, FunC contract won't compile |
| Performance | 8 / 10 | Acceptable; raw_feeds bloat is documented |
| Quality | 7 / 10 | Drift risk across 3 ports; FunC scaffold is partial |

## R²S² gate
- **Robust:** ⚠ shell scripts fail silently on non-PicoClaw platforms
- **Reliable:** ✅ 14/14 tests pass on Python core
- **Solid:** ⚠ FunC contract incomplete (won't compile as-is)
- **Stable:** ✅ no breaking changes vs v0.1.0
- **Resistant:** ⚠ `bc` failure swallowed in bridge
- **Scalable:** ✅ ARM64 + multi-arch image ready
- **Secure:** ✅ no secrets, no injection vectors
- **Systematic:** ✅ blueprint, tests, CI workflow in place
