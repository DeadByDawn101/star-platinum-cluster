#!/usr/bin/env bash
# ============================================================================
# STAR PLATINUM CLUSTER — Phase 1: exo Cluster Bringup
# ============================================================================
#
# Run this script on EACH Mac node in the cluster.
# It installs prerequisites, clones exo, builds the dashboard,
# configures Thunderbolt networking, and starts exo.
#
# IMPORTANT: This uses exo's TCP/Thunderbolt networking mode (not RDMA).
# Apple's RDMA requires TB5 on BOTH ends of each cable. Your cluster has:
#   - M4 Max: TB5 (only TB5 node)
#   - M3: TB4
#   - M2 Pro: TB4
#   - iMac Pro: TB3
# RDMA requires TB5↔TB5 links, so TCP over Thunderbolt is the correct
# transport for this cluster. Still 40 Gbps — just higher latency than RDMA.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/DeadByDawn101/star-platinum-cluster/main/scripts/phase1_setup.sh | bash
#
# Or clone and run:
#   git clone https://github.com/DeadByDawn101/star-platinum-cluster
#   cd star-platinum-cluster
#   bash scripts/phase1_setup.sh
#
# ============================================================================

set -euo pipefail

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${CYAN}[spc]${NC} $1"; }
ok()   { echo -e "${GREEN}[ok]${NC}  $1"; }
warn() { echo -e "${YELLOW}[!]${NC}  $1"; }
fail() { echo -e "${RED}[ERR]${NC} $1"; exit 1; }

# ─── Detect platform ────────────────────────────────────────────────

log "Detecting platform..."
if [[ "$(uname)" != "Darwin" ]]; then
  fail "This script is for macOS only. Beast Linux uses a different setup path."
fi

CHIP=$(sysctl -n machdep.cpu.brand_string 2>/dev/null || echo "unknown")
MEM_BYTES=$(sysctl -n hw.memsize 2>/dev/null || echo "0")
MEM_GB=$((MEM_BYTES / 1073741824))
MACOS_VER=$(sw_vers -productVersion 2>/dev/null || echo "unknown")
HOSTNAME=$(hostname -s)

ok "Host: $HOSTNAME"
ok "Chip: $CHIP"
ok "Memory: ${MEM_GB} GB"
ok "macOS: $MACOS_VER"

# ─── Check for Apple Silicon (ANE nodes) vs Intel (iMac Pro) ────────

IS_APPLE_SILICON=false
if sysctl -n hw.optional.arm64 2>/dev/null | grep -q "1"; then
  IS_APPLE_SILICON=true
  ok "Apple Silicon detected — ANE compute available"
else
  warn "Intel detected — no ANE, GPU-only compute (iMac Pro)"
fi

# ─── Step 1: Install Homebrew if missing ─────────────────────────────

log "Step 1: Checking Homebrew..."
if command -v brew &>/dev/null; then
  ok "Homebrew already installed"
else
  log "Installing Homebrew..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  # Add to PATH for Apple Silicon
  if [[ -f /opt/homebrew/bin/brew ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  fi
  ok "Homebrew installed"
fi

# ─── Step 2: Install prerequisites ───────────────────────────────────

log "Step 2: Installing prerequisites..."
brew install uv node 2>/dev/null || true

if $IS_APPLE_SILICON; then
  brew install macmon 2>/dev/null || true
  ok "macmon installed (Apple Silicon hardware monitoring)"
else
  warn "Skipping macmon (Intel — not supported)"
fi

# Install Rust if missing
if ! command -v rustc &>/dev/null; then
  log "Installing Rust..."
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
  source "$HOME/.cargo/env"
fi
rustup toolchain install nightly 2>/dev/null || true
ok "Prerequisites installed (uv, node, rust nightly)"

# ─── Step 3: Check Xcode CLI tools ──────────────────────────────────

log "Step 3: Checking Xcode Command Line Tools..."
if xcode-select -p &>/dev/null; then
  ok "Xcode CLI tools present"
else
  log "Installing Xcode CLI tools (this may prompt a dialog)..."
  xcode-select --install 2>/dev/null || true
  warn "Accept the Xcode dialog if prompted, then re-run this script"
fi

# ─── Step 4: Clone exo ──────────────────────────────────────────────

EXO_DIR="$HOME/Projects/exo"
log "Step 4: Setting up exo at $EXO_DIR..."

if [[ -d "$EXO_DIR" ]]; then
  log "exo directory exists, pulling latest..."
  cd "$EXO_DIR" && git pull origin main 2>/dev/null || true
else
  mkdir -p "$HOME/Projects"
  git clone https://github.com/DeadByDawn101/exo.git "$EXO_DIR"
fi
ok "exo source ready at $EXO_DIR"

# ─── Step 5: Build dashboard ────────────────────────────────────────

log "Step 5: Building exo dashboard..."
cd "$EXO_DIR/dashboard"
npm install 2>/dev/null
npm run build 2>/dev/null
cd "$EXO_DIR"
ok "Dashboard built"

# ─── Step 6: Configure Thunderbolt networking ────────────────────────

log "Step 6: Configuring Thunderbolt networking..."
log "This disables Thunderbolt Bridge and sets up per-port DHCP."
log "Required for exo peer discovery over Thunderbolt."

if [[ -f "$EXO_DIR/tmp/set_rdma_network_config.sh" ]]; then
  warn "Running set_rdma_network_config.sh (may require sudo)..."
  sudo bash "$EXO_DIR/tmp/set_rdma_network_config.sh" 2>/dev/null || {
    warn "TB network config script had issues — manual setup may be needed"
    warn "Key steps: disable Thunderbolt Bridge, set DHCP on each TB port"
  }
  ok "Thunderbolt networking configured"
else
  warn "set_rdma_network_config.sh not found — configure TB networking manually"
fi

# ─── Step 7: Clone star-platinum-cluster ─────────────────────────────

SPC_DIR="$HOME/Projects/star-platinum-cluster"
log "Step 7: Setting up star-platinum-cluster at $SPC_DIR..."

if [[ -d "$SPC_DIR" ]]; then
  cd "$SPC_DIR" && git pull origin main 2>/dev/null || true
else
  git clone https://github.com/DeadByDawn101/star-platinum-cluster.git "$SPC_DIR"
fi
ok "star-platinum-cluster ready"

# ─── Step 8: Clone ANE repo (Apple Silicon only) ────────────────────

if $IS_APPLE_SILICON; then
  ANE_DIR="$HOME/Projects/ANE"
  log "Step 8: Setting up ANE at $ANE_DIR..."
  if [[ -d "$ANE_DIR" ]]; then
    cd "$ANE_DIR" && git pull origin main 2>/dev/null || true
  else
    git clone https://github.com/DeadByDawn101/ANE.git "$ANE_DIR"
  fi
  ok "ANE repo ready"

  # Build bridge dylib if possible
  if [[ -f "$ANE_DIR/bridge/Makefile" ]]; then
    log "Building ANE bridge dylib..."
    cd "$ANE_DIR/bridge" && make 2>/dev/null && ok "libane_bridge.dylib built" || warn "ANE bridge build failed — will use software fallback"
  fi
else
  log "Step 8: Skipping ANE setup (Intel node)"
fi

# ─── Step 9: Verify Thunderbolt connections ──────────────────────────

log "Step 9: Checking Thunderbolt connections..."
if system_profiler SPThunderboltDataType 2>/dev/null | grep -q "Peer"; then
  ok "Thunderbolt peer(s) detected!"
  system_profiler SPThunderboltDataType 2>/dev/null | grep -E "Device Name|Peer" | head -10
else
  warn "No Thunderbolt peers detected. Make sure cables are connected."
  warn "After connecting cables, exo will discover peers via mDNS."
fi

# ─── Step 10: Test exo startup ───────────────────────────────────────

log "Step 10: Testing exo startup..."
cd "$EXO_DIR"

log "Starting exo (will run for 10 seconds to verify)..."
timeout 10 uv run exo 2>&1 | head -20 || true
ok "exo startup test complete"

# ─── Summary ─────────────────────────────────────────────────────────

echo ""
echo "============================================================================"
echo -e "${GREEN} Phase 1 setup complete for: $HOSTNAME ${NC}"
echo "============================================================================"
echo ""
echo "  Node:     $HOSTNAME"
echo "  Chip:     $CHIP"
echo "  Memory:   ${MEM_GB} GB"
echo "  macOS:    $MACOS_VER"
echo "  Silicon:  $(if $IS_APPLE_SILICON; then echo 'Apple Silicon (ANE available)'; else echo 'Intel (GPU only)'; fi)"
echo ""
echo "  To start exo:"
echo "    cd $EXO_DIR && uv run exo"
echo ""
echo "  Dashboard: http://localhost:52415"
echo ""
echo "  TRANSPORT MODE: TCP over Thunderbolt (40 Gbps)"
echo "  (RDMA requires TB5 on both ends — only M4 Max has TB5)"
echo ""
echo "  Next: Run this script on ALL other nodes, then verify"
echo "  cluster discovery in the exo dashboard."
echo "============================================================================"
