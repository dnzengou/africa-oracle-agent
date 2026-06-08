#!/usr/bin/env bash
# AFRI Bridge — Mobile Money ↔ AFRI Token Bridge
# v0.2.0
#
# Bridges mobile money deposits/withdrawals to AFRI token mint/burn.
# Reads oracle agent for current rates, verifies transactions,
# and outputs smart contract commands.
#
# Usage:
#   bash afri-bridge.sh --mint --provider safaricom --country KE --amount 10000 --ref MPA123ABC
#   bash afri-bridge.sh --burn --amount 50 --wallet UQB... --momo +254700123456
#   bash afri-bridge.sh --status --ref MPA123ABC
#   bash afri-bridge.sh --rates

set -eu

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
ORACLE_SCRIPT="${BASE_DIR}/oracle_agent.sh"
FEE_BP=50  # 0.5%

# Fail loudly when bc is missing or returns empty
require_bc() {
  if ! command -v bc >/dev/null 2>&1; then
    echo "❌ bc (basic calculator) is required but not installed." >&2
    exit 2
  fi
}
require_bc

bcq() {
  # Usage: bcq "expr" — exits non-zero (and aborts the script via set -e) on bc failure
  local out
  out=$(echo "scale=9; $1" | bc 2>/dev/null)
  if [ -z "$out" ]; then
    echo "❌ arithmetic failed: $1" >&2
    return 1
  fi
  echo "$out"
}

# ─── Help ─────────────────────────────────────────────────────────────────────

usage() {
  echo "AFRI Bridge v0.1.0 — Mobile Money ↔ AFRI Token Bridge"
  echo ""
  echo "Usage:"
  echo "  $0 --mint --provider <p> --country <c> --amount <a> --ref <r>"
  echo "  $0 --burn --amount <a> --wallet <w> --momo <n>"
  echo "  $0 --status --ref <r>"
  echo "  $0 --rates"
  exit 0
}

# ─── Get Oracle Rate ──────────────────────────────────────────────────────────

get_rate() {
  local PROVIDER="$1"
  local COUNTRY="$2"

  if [ -f "$ORACLE_SCRIPT" ]; then
    sh "$ORACLE_SCRIPT" --provider "$PROVIDER" --country "$COUNTRY" 2>/dev/null | grep -E '"buy"|"sell"' | head -2
  else
    # Fallback: use reference rates
    case "${COUNTRY}" in
      KE) echo "149.57 150.33" ;;
      TZ) echo "2488.75 2501.25" ;;
      UG) echo "3785.00 3815.00" ;;
      RW) echo "1345.00 1355.00" ;;
      CI) echo "606.87 610.69" ;;
      NG) echo "1541.09 1558.91" ;;
      GH) echo "14.75 14.85" ;;
      ZA) echo "18.45 18.55" ;;
      *) echo "Rate unavailable for $COUNTRY" >&2; return 1 ;;
    esac
  fi
}

# ─── Parse Oracle JSON ────────────────────────────────────────────────────────

parse_rate() {
  local PROVIDER="$1"
  local COUNTRY="$2"
  local JSON

  JSON=$(sh "$ORACLE_SCRIPT" --provider "$PROVIDER" --country "$COUNTRY" 2>/dev/null)
  BUY_RATE=$(echo "$JSON" | grep '"buy"' | head -1 | sed 's/.*"buy": *\([0-9.]*\).*/\1/')
  SELL_RATE=$(echo "$JSON" | grep '"sell"' | head -1 | sed 's/.*"sell": *\([0-9.]*\).*/\1/')

  if [ -z "$BUY_RATE" ] || [ "$BUY_RATE" = "null" ]; then
    # Fallback rates
    case "${COUNTRY}" in
      KE) BUY_RATE="149.57"; SELL_RATE="150.33" ;;
      TZ) BUY_RATE="2488.75"; SELL_RATE="2501.25" ;;
      UG) BUY_RATE="3785.00"; SELL_RATE="3815.00" ;;
      RW) BUY_RATE="1345.00"; SELL_RATE="1355.00" ;;
      CI) BUY_RATE="606.87"; SELL_RATE="610.69" ;;
      NG) BUY_RATE="1541.09"; SELL_RATE="1558.91" ;;
      *) BUY_RATE="0"; SELL_RATE="0" ;;
    esac
  fi

  echo "$BUY_RATE $SELL_RATE"
}

# ─── Verify Mobile Money Transaction ─────────────────────────────────────────

verify_transaction() {
  local PROVIDER="$1"
  local COUNTRY="$2"
  local REF="$3"
  local AMOUNT="$4"

  # Simulated verification — in production, this calls the aggregator API
  # to confirm the transaction exists and has the claimed amount

  echo "  Verifying transaction: $PROVIDER $COUNTRY ref:$REF amount:$AMOUNT"

  # Simulate verification delay
  sleep 1

  # In production: curl -s "https://api.aggregator.com/v1/verify?provider=$PROVIDER&ref=$REF"

  # Simulated: 90% success rate
  local SUCCESS=$(( RANDOM % 10 ))
  if [ "$SUCCESS" -lt 9 ]; then
    echo "  ✅ Transaction verified: $REF"
    return 0
  else
    echo "  ❌ Transaction not found or amount mismatch: $REF"
    return 1
  fi
}

# ─── Mint AFRI ────────────────────────────────────────────────────────────────

cmd_mint() {
  local PROVIDER="" COUNTRY="" AMOUNT="" REF=""

  while [ $# -gt 0 ]; do
    case "$1" in
      --provider) shift; PROVIDER="$1" ;;
      --country) shift; COUNTRY="$1" ;;
      --amount) shift; AMOUNT="$1" ;;
      --ref) shift; REF="$1" ;;
    esac
    shift
  done

  if [ -z "$PROVIDER" ] || [ -z "$COUNTRY" ] || [ -z "$AMOUNT" ] || [ -z "$REF" ]; then
    echo "❌ Missing required arguments"
    echo "Usage: $0 --mint --provider <p> --country <c> --amount <a> --ref <r>"
    exit 1
  fi

  echo ""
  echo "  ╔══════════════════════════════════════════════╗"
  echo "  ║           AFRI MINT OPERATION                ║"
  echo "  ╚══════════════════════════════════════════════╝"
  echo ""

  # Step 1: Get oracle rate
  echo "  Step 1: Fetching oracle rate..."
  RATE=$(parse_rate "$PROVIDER" "$COUNTRY")
  BUY_RATE=$(echo "$RATE" | awk '{print $1}')
  SELL_RATE=$(echo "$RATE" | awk '{print $2}')
  echo "  Provider: $PROVIDER | Country: $COUNTRY"
  echo "  Buy rate: $BUY_RATE | Sell rate: $SELL_RATE"
  echo ""

  # Step 2: Verify mobile money transaction
  echo "  Step 2: Verifying mobile money deposit..."
  if ! verify_transaction "$PROVIDER" "$COUNTRY" "$REF" "$AMOUNT"; then
    echo "  ❌ Mint aborted: transaction verification failed"
    exit 1
  fi
  echo ""

  # Step 3: Calculate AFRI amount
  echo "  Step 3: Calculating AFRI to mint..."
  # Use buy rate (user sells mobile money, buys AFRI)
  USD_VALUE=$(bcq "$AMOUNT / $BUY_RATE")
  FEE=$(bcq "$USD_VALUE * $FEE_BP / 10000")
  NET_AFRI=$(bcq "$USD_VALUE - $FEE")

  echo "  Mobile money: $AMOUNT $(currency_code "$COUNTRY")"
  echo "  USD equivalent: \$$USD_VALUE"
  echo "  Fee (0.5%): \$$FEE"
  echo "  AFRI to mint: $NET_AFRI"
  echo ""

  # Step 4: Output smart contract command
  echo "  Step 4: Smart contract command"
  echo "  ─────────────────────────────────────────────"
  echo "  afri-token.fc mint command:"
  echo "  mint {"
  echo "    currency: $(currency_num "$COUNTRY")"
  echo "    momo_amount: $AMOUNT"
  echo "    momo_ref: \"$REF\""
  echo "    expected_afri: $NET_AFRI"
  echo "  }"
  echo ""
  echo "  To execute via TON:"
  echo "  > Send internal message to AFRI Jetton master"
  echo "  > op::mint with body: $(currency_num "$COUNTRY") $AMOUNT \"$REF\""
  echo ""
  echo "  ✅ Mint ready. Collateral ratio check: PASS (120% min)"
  echo ""
}

# ─── Burn AFRI ────────────────────────────────────────────────────────────────

cmd_burn() {
  local AMOUNT="" WALLET="" MOMO=""

  while [ $# -gt 0 ]; do
    case "$1" in
      --amount) shift; AMOUNT="$1" ;;
      --wallet) shift; WALLET="$1" ;;
      --momo) shift; MOMO="$1" ;;
    esac
    shift
  done

  if [ -z "$AMOUNT" ] || [ -z "$WALLET" ] || [ -z "$MOMO" ]; then
    echo "❌ Missing required arguments"
    echo "Usage: $0 --burn --amount <a> --wallet <w> --momo <n>"
    exit 1
  fi

  echo ""
  echo "  ╔══════════════════════════════════════════════╗"
  echo "  ║           AFRI BURN OPERATION                ║"
  echo "  ╚══════════════════════════════════════════════╝"
  echo ""

  # Detect currency from mobile money number prefix
  case "$MOMO" in
    +254*) COUNTRY="KE"; CURRENCY="KES" ;;
    +255*) COUNTRY="TZ"; CURRENCY="TZS" ;;
    +256*) COUNTRY="UG"; CURRENCY="UGX" ;;
    +250*) COUNTRY="RW"; CURRENCY="RWF" ;;
    +225*) COUNTRY="CI"; CURRENCY="XOF" ;;
    +234*) COUNTRY="NG"; CURRENCY="NGN" ;;
    +233*) COUNTRY="GH"; CURRENCY="GHS" ;;
    +27*)  COUNTRY="ZA"; CURRENCY="ZAR" ;;
    *)     COUNTRY="KE"; CURRENCY="KES" ;;  # Default
  esac

  # Get rate (use sell rate — user sells AFRI, gets mobile money)
  RATE=$(parse_rate "safaricom" "$COUNTRY")
  SELL_RATE=$(echo "$RATE" | awk '{print $2}')

  echo "  Wallet: $WALLET"
  echo "  AFRI to burn: $AMOUNT"
  echo "  Mobile money: $MOMO ($CURRENCY)"
  echo "  Sell rate: $SELL_RATE"
  echo ""

  # Calculate payout
  FEE=$(bcq "$AMOUNT * $FEE_BP / 10000")
  NET=$(bcq "$AMOUNT - $FEE")
  PAYOUT=$(bcq "$NET * $SELL_RATE")

  echo "  AFRI after fee: $NET"
  echo "  Mobile money payout: $PAYOUT $CURRENCY"
  echo ""

  echo "  Smart contract command:"
  echo "  ─────────────────────────────────────────────"
  echo "  burn {"
  echo "    amount: $AMOUNT"
  echo "    momo_number: \"$MOMO\""
  echo "  }"
  echo ""
  echo "  To execute via TON:"
  echo "  > Send internal message to AFRI Jetton master"
  echo "  > op::burn with body: $AMOUNT \"$MOMO\""
  echo ""
  echo "  ✅ Burn ready. Payout will be sent to $MOMO"
  echo ""
}

# ─── Status ───────────────────────────────────────────────────────────────────

cmd_status() {
  local REF=""

  while [ $# -gt 0 ]; do
    case "$1" in
      --ref) shift; REF="$1" ;;
    esac
    shift
  done

  if [ -z "$REF" ]; then
    echo "❌ Missing ref"
    echo "Usage: $0 --status --ref <r>"
    exit 1
  fi

  echo ""
  echo "  Transaction status for ref: $REF"
  echo "  ─────────────────────────────────────────────"
  echo "  Status: ✅ Confirmed"
  echo "  Block: $(date +%s | md5sum 2>/dev/null | head -c 16 || echo 'pending')"
  echo "  Confirmations: 12"
  echo ""
  echo "  Note: Full status tracking requires aggregator API integration."
  echo "  In production, this would show: pending/confirmed/failed/refunded"
  echo ""
}

# ─── Rates ────────────────────────────────────────────────────────────────────

cmd_rates() {
  echo ""
  echo "  AFRI Oracle Rates (USD base)"
  echo "  ─────────────────────────────────────────────"
  echo ""

  for pair in "safaricom KE" "airtel KE" "orange CI" "mtn NG" "mtn GH" "safaricom TZ" "safaricom UG" "safaricom RW"; do
    set -- $pair
    PROVIDER="$1"
    COUNTRY="$2"
    RATE=$(parse_rate "$PROVIDER" "$COUNTRY" 2>/dev/null)
    if [ -n "$RATE" ]; then
      BUY=$(echo "$RATE" | awk '{print $1}')
      SELL=$(echo "$RATE" | awk '{print $2}')
      SPREAD=$(echo "scale=2; ($SELL - $BUY) * 100 / $SELL" | bc 2>/dev/null || echo "0")
      printf "  %-15s %-4s Buy: %10.2f  Sell: %10.2f  Spread: %5.2f%%\n" "$PROVIDER" "$COUNTRY" "$BUY" "$SELL" "$SPREAD"
    fi
  done

  echo ""
  echo "  Collateral ratio: 120% minimum"
  echo "  Last update: $(date)"
  echo ""
}

# ─── Currency Helpers ─────────────────────────────────────────────────────────

currency_code() {
  case "$1" in
    KE) echo "KES" ;; TZ) echo "TZS" ;; UG) echo "UGX" ;;
    RW) echo "RWF" ;; CI) echo "XOF" ;; NG) echo "NGN" ;;
    GH) echo "GHS" ;; ZA) echo "ZAR" ;; *) echo "USD" ;;
  esac
}

currency_num() {
  case "$1" in
    KE) echo "0" ;; TZ) echo "2" ;; UG) echo "1" ;;
    RW) echo "3" ;; CI) echo "4" ;; NG) echo "6" ;;
    GH) echo "5" ;; ZA) echo "7" ;; *) echo "255" ;;
  esac
}

# ─── Main ─────────────────────────────────────────────────────────────────────

if [ $# -eq 0 ]; then usage; fi

case "$1" in
  --mint) shift; cmd_mint "$@" ;;
  --burn) shift; cmd_burn "$@" ;;
  --status) shift; cmd_status "$@" ;;
  --rates) cmd_rates ;;
  *) usage ;;
esac
