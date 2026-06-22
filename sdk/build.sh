#!/usr/bin/env bash
# Build all distribution artifacts.
# Outputs land in ./dist/ at repo root.

set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$PWD"
DIST="$ROOT/dist"
VER="0.4.0"

mkdir -p "$DIST"

log() { printf '\033[1;32m[build]\033[0m %s\n' "$*"; }

# ─── Placeholder icons (1×1 transparent PNG) ─────────────────────────────────
mkicons() {
  local target="$1"; shift
  mkdir -p "$target"
  for size in "$@"; do
    local path="$target/icon-${size}.png"
    [ -f "$path" ] && continue
    # 67-byte transparent PNG, valid IHDR (1×1) + IDAT + IEND
    printf '\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7V\x84\x00\x00\x00\x00IEND\xaeB`\x82' > "$path"
  done
}

mkicons "$ROOT/sdk/extension/icons" 16 32 48 128
mkicons "$ROOT/sdk/pwa/icons"      192 512

# ─── Python wheel ────────────────────────────────────────────────────────────
if command -v python3 >/dev/null 2>&1; then
  log "Python SDK → wheel"
  cp "$ROOT/skills/africa-oracle-devflow.md" "$ROOT/sdk/python/africa_oracle/_skill.md"
  (cd "$ROOT/sdk/python" && python3 -m pip install --quiet --upgrade build hatchling 2>/dev/null && python3 -m build --wheel --outdir "$DIST" >/dev/null 2>&1) \
    && log "  → dist/africa_oracle-${VER}-py3-none-any.whl" \
    || log "  ⚠ python build skipped (install: pip install build)"
fi

# ─── TS SDK (compile + npm pack) ─────────────────────────────────────────────
if command -v npm >/dev/null 2>&1; then
  log "TS SDK → npm tgz"
  (cd "$ROOT/sdk/typescript" && npm install --silent --no-fund --no-audit && npm run build --silent && npm pack --silent --pack-destination "$DIST") \
    && log "  → dist/afri-oracle-${VER}.tgz" \
    || log "  ⚠ npm build skipped"
fi

# ─── Browser extension zip ───────────────────────────────────────────────────
log "Browser extension → zip"
(cd "$ROOT/sdk/extension" && zip -qr "$DIST/afri-extension-${VER}.zip" . -x '*.DS_Store') \
  && log "  → dist/afri-extension-${VER}.zip"

# ─── PWA tarball (static host upload) ────────────────────────────────────────
log "PWA → tarball"
tar -C "$ROOT/sdk" -czf "$DIST/afri-pwa-${VER}.tgz" pwa
log "  → dist/afri-pwa-${VER}.tgz"

# ─── VSCode VSIX ─────────────────────────────────────────────────────────────
if command -v vsce >/dev/null 2>&1; then
  log "VSCode → vsix"
  (cd "$ROOT/sdk/vscode" && vsce package --out "$DIST/afri-oracle-${VER}.vsix" >/dev/null 2>&1) \
    && log "  → dist/afri-oracle-${VER}.vsix"
else
  log "  ⚠ vsce not installed — skip vsix (npm i -g @vscode/vsce)"
fi

log "Built artifacts:"
ls -lh "$DIST" | tail -n +2 | awk '{ printf "  %s  %s\n", $5, $NF }'
