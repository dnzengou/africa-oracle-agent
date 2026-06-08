#!/bin/sh
# Africa Oracle Extraction Agent v0.1.0
# Shell implementation — runs on any POSIX system with curl/wget or web_fetch
#
# Phase 0: Mobile Money Oracle Bootstrapping
# Extracts simulated price feeds from mobile money aggregator APIs.
#
# Usage:
#   sh oracle_agent.sh --provider safaricom --country KE
#   sh oracle_agent.sh --all --pretty

set -e

# ─── Provider Configuration ───────────────────────────────────────────────────

PROVIDERS='{
  "safaricom": {"name":"Safaricom M-Pesa","countries":"KE,TZ,UG,RW,ZA,GH,CD,LS,MZ,SO","currencies":"KES,TZS,UGX,RWF,ZAR,GHS,CDF,LSL,MZN,SOS","agents":15000},
  "airtel": {"name":"Airtel Money","countries":"KE,UG,RW,ZA,CD,NE,GA,CG,TD","currencies":"KES,UGX,RWF,ZAR,CDF,XOF,XAF,XAF,XAF","agents":8000},
  "orange": {"name":"Orange Money","countries":"CI,SN,ML,BF,NE,BJ,TG,CM,MG","currencies":"XOF,XOF,XOF,XOF,XOF,XOF,XOF,XAF,MGA","agents":12000},
  "mtn": {"name":"MTN MoMo","countries":"GH,UG,RW,ZA,CI,NG,CM,ZM","currencies":"GHS,UGX,RWF,ZAR,XOF,NGN,XAF,ZMW","agents":10000}
}'

# Reference rates (USD base)
REF_KES=150.25  REF_TZS=2500.00  REF_UGX=3800.00  REF_RWF=1350.00
REF_ZAR=18.50   REF_GHS=14.80    REF_CDF=2800.00   REF_LSL=18.50
REF_MZN=64.00   REF_SOS=570.00   REF_XOF=610.00    REF_XAF=610.00
REF_MGA=4600.00 REF_NGN=1550.00  REF_ZMW=25.00

get_ref() {
  ccy="$1"
  eval "echo \"\$REF_${ccy}\""
}

# ─── Help ─────────────────────────────────────────────────────────────────────

usage() {
  echo "Africa Oracle Extraction Agent v0.1.0"
  echo ""
  echo "Usage: $0 [options]"
  echo "  --provider <name>  Mobile money provider (safaricom, airtel, orange, mtn)"
  echo "  --country <code>   Country code (KE, NG, GH, etc.)"
  echo "  --all              Run all provider/country combinations"
  echo "  --pretty           Pretty-print JSON output"
  echo "  --output <file>    Output file (default: stdout)"
  echo "  --interval <sec>   Polling interval in seconds"
  echo ""
  echo "Examples:"
  echo "  $0 --provider safaricom --country KE"
  echo "  $0 --all --pretty"
  exit 0
}

# ─── Simulate Price Feed ─────────────────────────────────────────────────────

simulate_price() {
  provider="$1"
  country="$2"
  currency="$3"
  agents="$4"

  base_rate=$(get_ref "$currency")
  [ -z "$base_rate" ] && base_rate=1000

  # Agent density affects spread
  agent_density=$(echo "scale=4; $agents / 15000" | bc 2>/dev/null || echo "1.0")
  [ "$(echo "$agent_density > 0" | bc 2>/dev/null)" = "0" ] && agent_density=1.0

  base_spread=$(echo "scale=6; 0.005 / $agent_density" | bc 2>/dev/null || echo "0.005")

  # Random noise using shell RNG
  noise_pct=$(echo "scale=4; ($RANDOM % 200 - 100) * 0.002 / 100" | bc 2>/dev/null || echo "0")
  noise=$(echo "scale=4; $base_rate * $noise_pct" | bc 2>/dev/null || echo "0")

  buy_price=$(echo "scale=4; $base_rate - ($base_rate * $base_spread / 2) + $noise" | bc 2>/dev/null || echo "$base_rate")
  sell_price=$(echo "scale=4; $base_rate + ($base_rate * $base_spread / 2) + $noise" | bc 2>/dev/null || echo "$base_rate")
  mid_price=$(echo "scale=4; ($buy_price + $sell_price) / 2" | bc 2>/dev/null || echo "$base_rate")
  spread=$(echo "scale=6; ($sell_price - $buy_price) / $buy_price" | bc 2>/dev/null || echo "0.005")
  spread_bps=$(echo "scale=2; $spread * 10000" | bc 2>/dev/null || echo "50")

  # Volume
  hour=$(date +%H)
  africa_hour=$(( (hour + 2) % 24 ))
  vol_mult=1.0
  [ "$africa_hour" -ge 8 ] && [ "$africa_hour" -le 12 ] && vol_mult=2.0
  [ "$africa_hour" -ge 14 ] && [ "$africa_hour" -le 18 ] && vol_mult=2.5
  [ "$africa_hour" -ge 22 ] || [ "$africa_hour" -le 5 ] && vol_mult=0.3

  vol_base=$(echo "scale=2; $RANDOM * 500000 / 32767 + 500000" | bc 2>/dev/null || echo "1000000")
  volume=$(echo "scale=2; $vol_base * $vol_mult * $agent_density" | bc 2>/dev/null || echo "$vol_base")

  confidence=$(echo "scale=4; 0.85 + $agent_density * 0.1" | bc 2>/dev/null || echo "0.95")
  [ "$(echo "$confidence > 0.99" | bc 2>/dev/null)" = "1" ] && confidence=0.99

  sources=$(( 50 + (RANDOM % agents / 100) ))
  timestamp=$(date +%s)
  datetime=$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u +%Y-%m-%dT%H:%M:%S)

  # Agent ID (simplified hash)
  agent_id=$(echo "$provider:$country:$timestamp" | sha256sum 2>/dev/null | cut -c1-16 || echo "agent_${RANDOM}")

  # Output JSON line
  cat << EOF
{
  "provider": "$provider",
  "country": "$country",
  "currency": "$currency",
  "timestamp": $timestamp,
  "datetime": "$datetime",
  "buy_price": $(echo "$buy_price" | sed 's/^\./0./'),
  "sell_price": $(echo "$sell_price" | sed 's/^\./0./'),
  "mid_price": $(echo "$mid_price" | sed 's/^\./0./'),
  "spread": $(echo "$spread" | sed 's/^\./0./'),
  "spread_bps": $(echo "$spread_bps" | sed 's/^\./0./'),
  "volume_24h": $(echo "$volume" | sed 's/^\./0./'),
  "confidence": $(echo "$confidence" | sed 's/^\./0./'),
  "sources": $sources,
  "agent_id": "$agent_id",
  "simulated": true
}
EOF
}

# ─── Aggregate ────────────────────────────────────────────────────────────────

get_json_val() {
  key="$1"
  shift
  echo "$@" | grep -o "\"$key\": [0-9.]*" | head -1 | awk '{print $2}'
}

# ─── Main ─────────────────────────────────────────────────────────────────────

PROVIDER=""
COUNTRY=""
ALL=false
PRETTY=false
OUTPUT=""
INTERVAL=0

while [ $# -gt 0 ]; do
  case "$1" in
    --provider) shift; PROVIDER="$1" ;;
    --country) shift; COUNTRY="$1" ;;
    --all) ALL=true ;;
    --pretty) PRETTY=true ;;
    --output) shift; OUTPUT="$1" ;;
    --interval) shift; INTERVAL="$1" ;;
    --help|-h) usage ;;
    *) echo "Unknown option: $1"; usage ;;
  esac
  shift
done

# ─── Generate Feeds ──────────────────────────────────────────────────────────

generate_feeds() {
  if [ "$ALL" = true ]; then
    # Safaricom
    simulate_price "Safaricom M-Pesa" "KE" "KES" 15000
    simulate_price "Safaricom M-Pesa" "TZ" "TZS" 15000
    simulate_price "Safaricom M-Pesa" "UG" "UGX" 15000
    simulate_price "Safaricom M-Pesa" "RW" "RWF" 15000
    simulate_price "Safaricom M-Pesa" "ZA" "ZAR" 15000
    simulate_price "Safaricom M-Pesa" "GH" "GHS" 15000
    # Airtel
    simulate_price "Airtel Money" "KE" "KES" 8000
    simulate_price "Airtel Money" "UG" "UGX" 8000
    simulate_price "Airtel Money" "RW" "RWF" 8000
    simulate_price "Airtel Money" "ZA" "ZAR" 8000
    # Orange
    simulate_price "Orange Money" "CI" "XOF" 12000
    simulate_price "Orange Money" "SN" "XOF" 12000
    simulate_price "Orange Money" "CM" "XAF" 12000
    simulate_price "Orange Money" "MG" "MGA" 12000
    # MTN
    simulate_price "MTN MoMo" "GH" "GHS" 10000
    simulate_price "MTN MoMo" "UG" "UGX" 10000
    simulate_price "MTN MoMo" "NG" "NGN" 10000
    simulate_price "MTN MoMo" "ZA" "ZAR" 10000
  elif [ -n "$PROVIDER" ] && [ -n "$COUNTRY" ]; then
    # Look up agents count
    case "$PROVIDER" in
      safaricom) AGENTS=15000 ;;
      airtel)    AGENTS=8000 ;;
      orange)    AGENTS=12000 ;;
      mtn)       AGENTS=10000 ;;
      *)         AGENTS=5000 ;;
    esac
    # Look up currency
    case "${PROVIDER}_${COUNTRY}" in
      safaricom_KE) CUR="KES" ;; safaricom_TZ) CUR="TZS" ;; safaricom_UG) CUR="UGX" ;;
      safaricom_RW) CUR="RWF" ;; safaricom_ZA) CUR="ZAR" ;; safaricom_GH) CUR="GHS" ;;
      airtel_KE) CUR="KES" ;; airtel_UG) CUR="UGX" ;; airtel_RW) CUR="RWF" ;;
      airtel_ZA) CUR="ZAR" ;;
      orange_CI|orange_SN|orange_ML) CUR="XOF" ;; orange_CM) CUR="XAF" ;; orange_MG) CUR="MGA" ;;
      mtn_GH) CUR="GHS" ;; mtn_UG) CUR="UGX" ;; mtn_NG) CUR="NGN" ;; mtn_ZA) CUR="ZAR" ;;
      *) CUR="USD" ;;
    esac
    simulate_price "$PROVIDER" "$COUNTRY" "$CUR" "$AGENTS"
  else
    usage
  fi
}

# ─── Output ───────────────────────────────────────────────────────────────────

output_data() {
  if [ -n "$OUTPUT" ]; then
    generate_feeds >> "$OUTPUT"
  else
    generate_feeds
  fi
}

# One-shot or interval
if [ "$INTERVAL" -gt 0 ]; then
  while true; do
    output_data
    sleep "$INTERVAL"
  done
else
  output_data
fi
