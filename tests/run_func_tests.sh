#!/usr/bin/env bash
# tests/run_func_tests.sh — Compile + smoke-check FunC tests for afri-token.fc
# v0.1.0
#
# Pure-helper tests live in tests/test_afri_token_funcs.fc. Each test method
# returns 0 on PASS, non-zero on FAIL (the drift value, for debugging).
#
# This runner:
#   1. Verifies the FunC toolchain (func, fift) is installed.
#   2. Compiles the test file (which #includes ../afri-token.fc).
#   3. Assembles it to a BoC via fift — proves the contract image is valid.
#   4. Prints next-step instructions for execution via toncli or lite-client.
#
# Why no TVM execution here: invoking method_ids requires either toncli's
# sandbox emulator or a deployed contract on testnet. Both are heavier than a
# CI smoke check needs to be. The compile + assemble gate catches every issue
# that would prevent the contract from running at all.

set -eu

DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$DIR")"
BUILD="$ROOT/build/tests"

# stdlib resolution: honour env, fall back to common system paths, then repo root.
FUNC_STDLIB="${FUNC_STDLIB:-}"
if [ -z "$FUNC_STDLIB" ]; then
  for cand in \
    /usr/lib/fift/stdlib.fc \
    /usr/local/lib/fift/stdlib.fc \
    /opt/ton/crypto/smartcont/stdlib.fc \
    "$ROOT/stdlib.fc"; do
    if [ -f "$cand" ]; then
      FUNC_STDLIB="$cand"
      break
    fi
  done
fi

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo ""
echo "  AFRI Token — FunC unit-test compile gate"
echo "  ─────────────────────────────────────────────"

# ─── Toolchain check ─────────────────────────────────────────────────────────

MISSING=0
if ! command -v func >/dev/null 2>&1; then
  printf "  ${RED}✗${NC} func not in PATH\n"
  MISSING=1
else
  printf "  ${GREEN}✓${NC} func: %s\n" "$(func --version 2>&1 || echo unknown)"
fi

if ! command -v fift >/dev/null 2>&1; then
  printf "  ${RED}✗${NC} fift not in PATH\n"
  MISSING=1
else
  printf "  ${GREEN}✓${NC} fift present\n"
fi

if [ -z "$FUNC_STDLIB" ] || [ ! -f "$FUNC_STDLIB" ]; then
  printf "  ${RED}✗${NC} stdlib.fc not found (tried env FUNC_STDLIB + common paths)\n"
  printf "  ${YELLOW}→${NC} Set FUNC_STDLIB=/path/to/stdlib.fc and retry.\n"
  MISSING=1
else
  printf "  ${GREEN}✓${NC} stdlib.fc: %s\n" "$FUNC_STDLIB"
fi

if [ "$MISSING" -eq 1 ]; then
  echo ""
  printf "  ${YELLOW}⚠${NC} Toolchain missing — skipping compile.\n"
  printf "  Install: https://docs.ton.org/develop/howto/compile\n"
  echo ""
  exit 1
fi

mkdir -p "$BUILD"

# ─── Compile ─────────────────────────────────────────────────────────────────

echo ""
echo "  Compiling tests/test_afri_token_funcs.fc..."
func -SPA -o "$BUILD/test_afri_token_funcs.fif" \
  "$FUNC_STDLIB" \
  "$DIR/test_afri_token_funcs.fc"
printf "  ${GREEN}✓${NC} Compiled → %s\n" "$BUILD/test_afri_token_funcs.fif"

# ─── Assemble (proves the contract image is valid BoC) ───────────────────────

echo ""
echo "  Assembling to BoC..."
if fift -s "$BUILD/test_afri_token_funcs.fif" >"$BUILD/assemble.log" 2>&1; then
  printf "  ${GREEN}✓${NC} BoC assembled (see %s)\n" "$BUILD/assemble.log"
else
  printf "  ${RED}✗${NC} Assembly failed — see %s\n" "$BUILD/assemble.log"
  exit 1
fi

# ─── Next steps ──────────────────────────────────────────────────────────────

echo ""
echo "  ─────────────────────────────────────────────"
echo "  Compile gate: ${GREEN}PASS${NC}"
echo ""
echo "  To execute the 7 unit tests (each returns 0 on PASS):"
echo ""
echo "    # Option A — toncli sandbox emulator:"
echo "    toncli run_tests"
echo ""
echo "    # Option B — deployed test contract on testnet:"
echo "    bash afri-deploy.sh                  # deploy contract"
echo "    lite-client -C testnet-config.json -a testnet.toncenter.com:49241"
echo "    > runmethod <addr> 100               # test_mint_at_par_kes"
echo "    > runmethod <addr> 101               # test_mint_small_xof"
echo "    > runmethod <addr> 102               # test_burn_at_par_kes"
echo "    > runmethod <addr> 103               # test_collateral_at_boundary"
echo "    > runmethod <addr> 104               # test_collateral_breach"
echo "    > runmethod <addr> 105               # test_collateral_empty_supply"
echo "    > runmethod <addr> 106               # test_mint_then_burn_roundtrip"
echo ""
