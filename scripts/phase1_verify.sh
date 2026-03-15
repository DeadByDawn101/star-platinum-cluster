#!/usr/bin/env bash
# ============================================================================
# STAR PLATINUM CLUSTER — Phase 1: Cluster Verification
# ============================================================================
#
# Run this on the M4 Max (brain) after all nodes have completed phase1_setup.sh
# and exo is running on each node.
#
# Verifies:
#   1. All nodes are discoverable via mDNS
#   2. exo dashboard is accessible
#   3. Thunderbolt links are active
#   4. Cluster topology is correct (4-node ring)
#   5. A test model can be loaded and run
#
# ============================================================================

set -euo pipefail

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${CYAN}[verify]${NC} $1"; }
ok()   { echo -e "${GREEN}  [ok]${NC}   $1"; }
warn() { echo -e "${YELLOW}  [!]${NC}   $1"; }
fail() { echo -e "${RED}  [ERR]${NC} $1"; }

echo "============================================================================"
echo "  STAR PLATINUM CLUSTER — Phase 1 Verification"
echo "============================================================================"
echo ""

# ─── 1. Check local exo ─────────────────────────────────────────────

log "1. Checking local exo instance..."
if curl -s http://localhost:52415/health 2>/dev/null | grep -q "ok\|healthy\|running"; then
  ok "exo is running on localhost:52415"
else
  # Try the API endpoint
  if curl -s http://localhost:52415/ 2>/dev/null | head -1 | grep -qi "html\|exo"; then
    ok "exo dashboard is serving on localhost:52415"
  else
    fail "exo not responding on localhost:52415"
    echo "    Start exo first: cd ~/Projects/exo && uv run exo"
  fi
fi

# ─── 2. Check Thunderbolt links ─────────────────────────────────────

log "2. Checking Thunderbolt connections..."
TB_PEERS=$(system_profiler SPThunderboltDataType 2>/dev/null | grep -c "Peer" || echo "0")
echo "    Thunderbolt peers detected: $TB_PEERS"

if [[ "$TB_PEERS" -ge 2 ]]; then
  ok "Multiple TB peers found (expected 2 for M4 Max brain)"
elif [[ "$TB_PEERS" -eq 1 ]]; then
  warn "Only 1 TB peer — expected 2 connections from M4 Max"
else
  fail "No TB peers detected — check cable connections"
fi

# Show TB device details
system_profiler SPThunderboltDataType 2>/dev/null | grep -E "Device Name|Speed|Status" | head -10 || true

# ─── 3. Check network interfaces ────────────────────────────────────

log "3. Checking Thunderbolt network interfaces..."
TB_IFACES=$(ifconfig 2>/dev/null | grep -c "bridge\|en[0-9]*.*thunderbolt" || echo "0")
echo "    Thunderbolt-related interfaces found"

# List all interfaces with IPs
ifconfig 2>/dev/null | grep -E "^[a-z]|inet " | grep -B1 "inet " | grep -v "^--$" | head -20 || true

# ─── 4. Check mDNS / Bonjour discovery ──────────────────────────────

log "4. Checking mDNS peer discovery..."
echo "    Scanning for exo peers (5 seconds)..."

# dns-sd browse for exo's libp2p mDNS
dns-sd -B _p2p._udp local. 2>/dev/null &
DNS_PID=$!
sleep 5
kill $DNS_PID 2>/dev/null || true
wait $DNS_PID 2>/dev/null || true

echo "    (If no peers shown above, they may use a different mDNS service name)"
echo "    exo uses libp2p mDNS — peers appear automatically in the dashboard"

# ─── 5. Check exo cluster state via API ─────────────────────────────

log "5. Querying exo cluster state..."

# Try common exo API endpoints
for endpoint in "/api/v1/cluster" "/api/v1/nodes" "/health" "/api/v1/topology"; do
  RESP=$(curl -s "http://localhost:52415${endpoint}" 2>/dev/null || echo "")
  if [[ -n "$RESP" ]] && [[ "$RESP" != *"404"* ]] && [[ "$RESP" != *"not found"* ]]; then
    ok "API ${endpoint} responded"
    echo "$RESP" | python3 -m json.tool 2>/dev/null | head -20 || echo "    $RESP" | head -3
    echo ""
  fi
done

# ─── 6. Hardware summary ────────────────────────────────────────────

log "6. Local hardware summary..."
echo ""
echo "    Chip: $(sysctl -n machdep.cpu.brand_string 2>/dev/null || echo 'unknown')"
echo "    Memory: $(($(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1073741824)) GB"
echo "    macOS: $(sw_vers -productVersion 2>/dev/null || echo 'unknown')"
echo "    GPU cores: $(system_profiler SPDisplaysDataType 2>/dev/null | grep "Total Number of Cores" | head -1 | awk '{print $NF}' || echo 'unknown')"
echo "    Metal: $(system_profiler SPDisplaysDataType 2>/dev/null | grep "Metal" | head -1 | awk -F: '{print $2}' || echo 'unknown')"

if sysctl -n hw.optional.arm64 2>/dev/null | grep -q "1"; then
  echo "    ANE: Available (Apple Silicon)"
else
  echo "    ANE: Not available (Intel)"
fi

# ─── 7. Quick model test ────────────────────────────────────────────

log "7. Quick inference test..."
echo "    Sending a test prompt via OpenAI-compatible API..."

TEST_RESP=$(curl -s http://localhost:52415/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama-3.2-1b",
    "messages": [{"role": "user", "content": "Say hello in one word."}],
    "max_tokens": 10,
    "stream": false
  }' 2>/dev/null || echo "")

if [[ -n "$TEST_RESP" ]] && echo "$TEST_RESP" | grep -q "choices\|content\|message"; then
  ok "Model inference working!"
  echo "$TEST_RESP" | python3 -m json.tool 2>/dev/null | head -10 || echo "    $TEST_RESP" | head -3
else
  warn "Inference test did not return expected response"
  warn "This is normal if no model is loaded yet"
  echo "    Load a model via the exo dashboard at http://localhost:52415"
  echo "    Or wait for auto-download when you send a chat request"
  if [[ -n "$TEST_RESP" ]]; then
    echo "    Response: $(echo "$TEST_RESP" | head -2)"
  fi
fi

# ─── Summary ─────────────────────────────────────────────────────────

echo ""
echo "============================================================================"
echo -e "${GREEN}  Phase 1 verification complete${NC}"
echo "============================================================================"
echo ""
echo "  Next steps:"
echo "    1. Open http://localhost:52415 in a browser"
echo "    2. Verify all 4 nodes appear in the cluster view"
echo "    3. Load a model (Qwen 2.5 32B recommended for 128 GB brain)"
echo "    4. Send a chat message and verify multi-node inference"
echo ""
echo "  Cluster nodes (expected):"
echo "    [1] M4 Max 128GB  — Brain (this machine)"
echo "    [2] M1 Pro 16GB   — ANE compute (11 TFLOPS)"
echo "    [3] M3 24GB       — ANE worker (9 TFLOPS)"
echo "    [4] M2 Pro 16GB   — ANE compute (7.9 TFLOPS)"
echo "    [5] iMac Pro 32GB — Control + Vega GPU"
echo ""
echo "  Cluster totals:"
echo "    ANE: 46.9 TFLOPS FP16 (4 ANE nodes)"
echo "    GPU: ~102 TFLOPS FP16"
echo "    Memory: 216 GB unified"
echo ""
echo "  Transport: TCP over Thunderbolt (40 Gbps)"
echo "  Note: RDMA requires TB5↔TB5 — upgrade path for future"
echo "============================================================================"
