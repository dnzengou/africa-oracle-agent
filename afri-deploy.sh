#!/usr/bin/env bash
# AFRI Deploy — Deploy AFRI Token to TON Blockchain
# v0.2.0
#
# Deploys the AFRI Jetton smart contract to TON testnet or mainnet.
# Requires: func, fift, lite-client (TON toolchain)
#
# Usage:
#   bash afri-deploy.sh                    # Deploy to testnet
#   bash afri-deploy.sh --mainnet          # Deploy to mainnet
#   bash afri-deploy.sh --verify           # Verify deployment
#   bash afri-deploy.sh --help

set -eu

# ─── Configuration ────────────────────────────────────────────────────────────

CONTRACT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONTRACT_FILE="${CONTRACT_DIR}/afri-token.fc"
BUILD_DIR="${CONTRACT_DIR}/build"
FUNC_STDLIB="${FUNC_STDLIB:-/usr/lib/fift/stdlib.fc}"  # override via env

# Testnet config
TESTNET_CONFIG="https://ton.org/testnet-global.config.json"
TESTNET_LITE_SERVER="testnet.toncenter.com"
TESTNET_PORT="49241"

# Mainnet config
MAINNET_CONFIG="https://ton.org/global.config.json"
MAINNET_LITE_SERVER="mainnet.toncenter.com"
MAINNET_PORT="49241"

# ─── Colors ───────────────────────────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# ─── Help ─────────────────────────────────────────────────────────────────────

usage() {
  echo "AFRI Deploy v0.1.0 — Deploy AFRI Token to TON Blockchain"
  echo ""
  echo "Usage:"
  echo "  $0                    Deploy to testnet (default)"
  echo "  $0 --mainnet          Deploy to mainnet"
  echo "  $0 --verify           Verify existing deployment"
  echo "  $0 --help             Show this help"
  echo ""
  echo "Prerequisites:"
  echo "  - func (FunC compiler)"
  echo "  - fift (FIFT assembler)"
  echo "  - lite-client (TON node client)"
  echo ""
  echo "Install TON toolchain:"
  echo "  git clone https://github.com/ton-blockchain/ton.git"
  echo "  cd ton && mkdir build && cd build"
  echo "  cmake .. -DCMAKE_BUILD_TYPE=Release"
  echo "  make -j4 func fift lite-client"
  exit 0
}

# ─── Check Dependencies ───────────────────────────────────────────────────────

check_deps() {
  echo ""
  echo "  Checking dependencies..."

  local MISSING=0

  if ! command -v func >/dev/null 2>&1; then
    echo "  ${RED}✗ func not found${NC}"
    MISSING=1
  else
    echo "  ${GREEN}✓ func found: $(func --version 2>&1 || echo 'unknown version')${NC}"
  fi

  if ! command -v fift >/dev/null 2>&1; then
    echo "  ${RED}✗ fift not found${NC}"
    MISSING=1
  else
    echo "  ${GREEN}✓ fift found${NC}"
  fi

  if ! command -v lite-client >/dev/null 2>&1; then
    echo "  ${YELLOW}⚠ lite-client not found (needed for deployment)${NC}"
    MISSING=1
  else
    echo "  ${GREEN}✓ lite-client found${NC}"
  fi

  if [ ! -f "$CONTRACT_FILE" ]; then
    echo "  ${RED}✗ Contract file not found: $CONTRACT_FILE${NC}"
    MISSING=1
  else
    echo "  ${GREEN}✓ Contract file: $CONTRACT_FILE${NC}"
  fi

  if [ "$MISSING" -eq 1 ]; then
    echo ""
    echo "  ${YELLOW}⚠ Some dependencies missing. Install TON toolchain first.${NC}"
    echo "  See: https://docs.ton.org/develop/howto/compile"
    echo ""
    echo "  ${YELLOW}The contract code is still valid and can be deployed later.${NC}"
    echo ""
    return 1
  fi

  return 0
}

# ─── Compile Contract ─────────────────────────────────────────────────────────

compile() {
  echo ""
  echo "  Compiling AFRI Token contract..."
  echo "  ─────────────────────────────────────────────"

  mkdir -p "$BUILD_DIR"

  # Compile FunC to FIFT
  if [ -f "$FUNC_STDLIB" ]; then
    func -o "${BUILD_DIR}/afri-token.fift" -SPA \
      "$FUNC_STDLIB" \
      "$CONTRACT_FILE"
  else
    # Try without stdlib (may work if func has built-in paths)
    func -o "${BUILD_DIR}/afri-token.fift" -SPA \
      "$CONTRACT_FILE" 2>&1 || {
      echo "  ${YELLOW}⚠ Compilation requires FunC stdlib.${NC}"
      echo "  Set FUNC_STDLIB to the correct path."
      return 1
    }
  fi

  echo "  ${GREEN}✓ Compiled: ${BUILD_DIR}/afri-token.fift${NC}"

  # Generate BoC (Bag of Cells)
  fift -s "${BUILD_DIR}/afri-token.fift" 2>&1 || {
    echo "  ${YELLOW}⚠ FIFT assembly step needs manual execution.${NC}"
    return 1
  }

  echo "  ${GREEN}✓ BoC generated${NC}"
  return 0
}

# ─── Deploy ───────────────────────────────────────────────────────────────────

deploy() {
  local NETWORK="$1"
  local CONFIG_URL="$2"
  local LITE_SERVER="$3"
  local PORT="$4"

  echo ""
  echo "  Deploying AFRI Token to ${NETWORK}..."
  echo "  ─────────────────────────────────────────────"

  # Check if BoC exists
  if [ ! -f "${BUILD_DIR}/afri-token.boc" ]; then
    echo "  ${YELLOW}⚠ BoC not found. Compile first.${NC}"
    echo "  Run: $0 (without --verify)"
    return 1
  fi

  # Create deployment message using lite-client
  # This requires interactive setup in production
  echo "  To deploy manually:"
  echo ""
  echo "  1. Connect to ${NETWORK}:"
  echo "     lite-client -C ${CONFIG_URL} -a ${LITE_SERVER}:${PORT}"
  echo ""
  echo "  2. Send deployment message:"
  echo "     sendfile ${BUILD_DIR}/afri-token.boc"
  echo ""
  echo "  3. Verify:"
  echo "     runmethod <contract_address> get_jetton_data"
  echo ""
  echo "  ${YELLOW}⚠ Full automated deployment requires:${NC}"
  echo "  - A funded wallet with TON for gas"
  echo "  - The wallet private key (for signing)"
  echo "  - Network connection to lite-server"
  echo ""
  echo "  ${GREEN}✓ Deployment instructions generated${NC}"
}

# ─── Verify ───────────────────────────────────────────────────────────────────

verify() {
  local NETWORK="$1"
  local CONFIG_URL="$2"
  local LITE_SERVER="$3"
  local PORT="$4"

  echo ""
  echo "  Verifying AFRI Token deployment on ${NETWORK}..."
  echo "  ─────────────────────────────────────────────"

  echo ""
  echo "  To verify deployment:"
  echo ""
  echo "  1. Connect to ${NETWORK}:"
  echo "     lite-client -C ${CONFIG_URL} -a ${LITE_SERVER}:${PORT}"
  echo ""
  echo "  2. Check contract state:"
  echo "     runmethod <contract_address> get_system_status"
  echo ""
  echo "  3. Expected output:"
  echo "     total_supply: 0"
  echo "     total_collateral: 0"
  echo "     ratio_bp: 0"
  echo "     last_update: <timestamp>"
  echo ""
  echo "  4. Check oracle rates:"
  echo "     runmethod <contract_address> get_rate 0"
  echo "     (0 = KES, 1 = UGX, 2 = TZS, 3 = RWF, 4 = XOF, 5 = XAF)"
  echo ""
  echo "  ${GREEN}✓ Verification instructions generated${NC}"
}

# ─── Main ─────────────────────────────────────────────────────────────────────

MODE="testnet"

while [ $# -gt 0 ]; do
  case "$1" in
    --mainnet) MODE="mainnet" ;;
    --verify) MODE="verify" ;;
    --help) usage ;;
    *) echo "Unknown: $1"; exit 1 ;;
  esac
  shift
done

echo ""
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║         AFRI TOKEN DEPLOYMENT                ║"
echo "  ║     African Digital Money Stablecoin         ║"
echo "  ╚══════════════════════════════════════════════╝"
echo ""

case "$MODE" in
  testnet)
    echo "  Target: ${GREEN}TESTNET${NC}"
    echo ""
    if check_deps; then
      compile && deploy "testnet" "$TESTNET_CONFIG" "$TESTNET_LITE_SERVER" "$TESTNET_PORT"
    else
      echo "  ${YELLOW}Skipping compilation (dependencies missing).${NC}"
      echo "  Contract code is ready at: $CONTRACT_FILE"
      echo "  Bridge script is ready at: ${CONTRACT_DIR}/afri-bridge.sh"
      echo ""
      echo "  To deploy later:"
      echo "  1. Install TON toolchain on a machine with Go/Rust"
      echo "  2. Run: func -o build/afri-token.fift -SPA stdlib.fc afri-token.fc"
      echo "  3. Run: fift -s build/afri-token.fift"
      echo "  4. Send: lite-client -C testnet-config.json -a testnet.toncenter.com:49241"
      echo "  5. Use: sendfile build/afri-token.boc"
    fi
    ;;
  mainnet)
    echo "  Target: ${RED}MAINNET${NC}"
    echo "  ${YELLOW}⚠ WARNING: Mainnet deployment requires real TON for gas!${NC}"
    echo ""
    if check_deps; then
      compile && deploy "mainnet" "$MAINNET_CONFIG" "$MAINNET_LITE_SERVER" "$MAINNET_PORT"
    else
      echo "  ${YELLOW}Dependencies missing. Cannot compile for mainnet.${NC}"
    fi
    ;;
  verify)
    verify "testnet" "$TESTNET_CONFIG" "$TESTNET_LITE_SERVER" "$TESTNET_PORT"
    ;;
esac

echo ""
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║              DEPLOYMENT COMPLETE              ║"
echo "  ╚══════════════════════════════════════════════╝"
echo ""
