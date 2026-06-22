#!/usr/bin/env sh
# AFRI Africa Oracle — one-liner installer for the POSIX edge port.
# Targets: Raspberry Pi (ARM64), Termux, generic Linux/BSD, PicoClaw.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/nzengou/africa-oracle-agent/main/sdk/installer/install.sh | sh
#
# Env:
#   AFRI_PREFIX   install prefix (default: $HOME/.local)
#   AFRI_BRANCH   git branch / ref (default: main)
#   AFRI_NO_DOCKER  set to skip Docker image pull on hosts with docker

set -eu

PREFIX="${AFRI_PREFIX:-$HOME/.local}"
BRANCH="${AFRI_BRANCH:-main}"
RAW="https://raw.githubusercontent.com/nzengou/africa-oracle-agent/${BRANCH}"
BIN_DIR="$PREFIX/bin"
SHARE_DIR="$PREFIX/share/africa-oracle"

log() { printf '\033[1;32m[afri]\033[0m %s\n' "$*"; }
err() { printf '\033[1;31m[afri]\033[0m %s\n' "$*" >&2; }

need() { command -v "$1" >/dev/null 2>&1 || { err "missing dep: $1"; exit 1; }; }
need curl
need sh

mkdir -p "$BIN_DIR" "$SHARE_DIR"

log "fetching oracle_agent.sh (POSIX edge port)…"
curl -fsSL "${RAW}/oracle_agent.sh" -o "$SHARE_DIR/oracle_agent.sh"
chmod +x "$SHARE_DIR/oracle_agent.sh"

log "fetching bridge + deploy harnesses…"
curl -fsSL "${RAW}/afri-bridge.sh"  -o "$SHARE_DIR/afri-bridge.sh"  && chmod +x "$SHARE_DIR/afri-bridge.sh"
curl -fsSL "${RAW}/afri-deploy.sh"  -o "$SHARE_DIR/afri-deploy.sh"  && chmod +x "$SHARE_DIR/afri-deploy.sh"

cat > "$BIN_DIR/afri" <<EOF
#!/usr/bin/env sh
exec "$SHARE_DIR/oracle_agent.sh" "\$@"
EOF
chmod +x "$BIN_DIR/afri"

# Optional: pull the multi-arch Docker image if docker is present
if [ -z "${AFRI_NO_DOCKER:-}" ] && command -v docker >/dev/null 2>&1; then
  log "pulling ghcr.io/nzengou/africa-oracle-agent:latest (ARM64-native if applicable)…"
  docker pull ghcr.io/nzengou/africa-oracle-agent:latest || \
    log "docker pull failed — skip (image will fall back to CLI mode)"
fi

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) log "add this to your shell rc:  export PATH=\"$BIN_DIR:\$PATH\"" ;;
esac

log "installed:"
log "  binary  $BIN_DIR/afri"
log "  share   $SHARE_DIR"
log "try:     afri --provider mtn --country GH"
