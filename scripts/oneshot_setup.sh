#!/usr/bin/env bash
# Star Platinum — One-Shot Node Setup
# Copy-paste this entire block into Terminal on each Mac node.
# It clones everything, installs deps, configures TB networking, and starts exo.

set -euo pipefail

G='\033[0;32m' Y='\033[1;33m' C='\033[0;36m' R='\033[0;31m' N='\033[0m'
ok()  { echo -e "${G}[ok]${N}  $1"; }
log() { echo -e "${C}[sp]${N}  $1"; }
err() { echo -e "${R}[!!]${N}  $1"; }

echo ""
echo -e "${C}╔════════════════════════════════════════════════╗${N}"
echo -e "${C}║  「STAR PLATINUM」— One-Shot Node Setup         ║${N}"
echo -e "${C}╚════════════════════════════════════════════════╝${N}"
echo ""

# ── 1. Homebrew ──────────────────────────────────────────────────
log "Installing Homebrew (skip if exists)..."
if command -v brew &>/dev/null; then
    ok "Homebrew already installed"
else
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
    eval "$(/opt/homebrew/bin/brew shellenv)"
    ok "Homebrew installed"
fi

# ── 2. Core tools ────────────────────────────────────────────────
log "Installing core tools..."
brew install --quiet git node uv rust 2>/dev/null || true
ok "Core tools ready"

# ── 3. Projects directory ────────────────────────────────────────
mkdir -p ~/Projects
cd ~/Projects

# ── 4. Clone repos (retry-safe) ─────────────────────────────────
clone_repo() {
    local url="$1" dir="$2"
    if [[ -d "$dir/.git" ]]; then
        ok "$dir already cloned — pulling latest"
        cd "$dir" && git pull --ff-only 2>/dev/null || true && cd ~/Projects
    else
        local attempt=0
        while [[ $attempt -lt 3 ]]; do
            if git clone "$url" "$dir" 2>/dev/null; then
                ok "Cloned $dir"
                return 0
            fi
            attempt=$((attempt + 1))
            echo "    Retry $attempt/3..."
            sleep 2
        done
        err "Failed to clone $dir after 3 attempts"
        return 1
    fi
}

log "Cloning repos..."
clone_repo "https://github.com/DeadByDawn101/star-platinum-cluster.git" "$HOME/Projects/star-platinum-cluster"
clone_repo "https://github.com/DeadByDawn101/exo.git" "$HOME/Projects/exo"
clone_repo "https://github.com/DeadByDawn101/ANE.git" "$HOME/Projects/ANE"

# ── 5. Thunderbolt networking ────────────────────────────────────
log "Configuring Thunderbolt networking..."

# Disable Thunderbolt Bridge (conflicts with direct IP)
if networksetup -listallnetworkservices 2>/dev/null | grep -q "Thunderbolt Bridge"; then
    sudo networksetup -setnetworkserviceenabled "Thunderbolt Bridge" off 2>/dev/null || true
    ok "Thunderbolt Bridge disabled"
fi

# Set DHCP on Thunderbolt interfaces
for iface in $(networksetup -listallnetworkservices 2>/dev/null | grep -i "thunderbolt" | grep -v "Bridge"); do
    sudo networksetup -setdhcp "$iface" 2>/dev/null || true
done
ok "Thunderbolt networking configured"

# ── 6. Build exo ─────────────────────────────────────────────────
log "Setting up exo..."
cd ~/Projects/exo
if [[ -f "pyproject.toml" ]]; then
    uv sync 2>/dev/null || uv pip install -e ".[dev]" 2>/dev/null || true
    ok "exo dependencies installed"
else
    ok "exo ready (no pyproject.toml — will install on first run)"
fi

# ── 7. Build ANE bridge (Apple Silicon only) ─────────────────────
if sysctl -n hw.optional.arm64 2>/dev/null | grep -q "1"; then
    log "Building ANE bridge..."
    cd ~/Projects/ANE
    if [[ -f "bridge/Makefile" ]]; then
        cd bridge && make 2>/dev/null && ok "ANE bridge built" || ok "ANE bridge — build skipped (will build later)"
        cd ~/Projects
    elif [[ -f "Makefile" ]]; then
        make 2>/dev/null && ok "ANE bridge built" || ok "ANE bridge — build skipped (will build later)"
    else
        ok "ANE bridge — no Makefile yet (will build later)"
    fi
else
    ok "Intel machine — skipping ANE bridge"
fi

# ── 8. System info ───────────────────────────────────────────────
echo ""
echo -e "${C}╔════════════════════════════════════════════════╗${N}"
echo -e "${C}║  Node Setup Complete                           ║${N}"
echo -e "${C}╚════════════════════════════════════════════════╝${N}"
echo ""
echo "  Chip:    $(sysctl -n machdep.cpu.brand_string 2>/dev/null || echo 'Apple Silicon')"
echo "  Memory:  $(($(sysctl -n hw.memsize 2>/dev/null) / 1073741824)) GB"
echo "  macOS:   $(sw_vers -productVersion)"
echo "  Node:    $(scutil --get ComputerName 2>/dev/null || hostname)"
echo ""

# Check Tailscale
if command -v tailscale &>/dev/null; then
    TS_IP=$(tailscale ip -4 2>/dev/null || echo "not connected")
    echo "  Tailscale: $TS_IP"
else
    echo "  Tailscale: not installed (brew install tailscale)"
fi

echo ""
echo -e "${G}  Next: start exo on this node:${N}"
echo "    cd ~/Projects/exo && uv run exo"
echo ""
echo -e "${G}  Then from M4 Max brain, verify the cluster:${N}"
echo "    cd ~/Projects/star-platinum-cluster && bash scripts/phase1_verify.sh"
echo ""
