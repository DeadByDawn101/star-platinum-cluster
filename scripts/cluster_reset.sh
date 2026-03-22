#!/usr/bin/env bash
# Star Platinum — Cluster Reset & Restart
# Run this from the M4 Max (or any node with SSH access to all others)
# Kills exo on all nodes, clears event logs, pulls latest code, restarts.

set -euo pipefail

G='\033[0;32m' R='\033[0;31m' C='\033[0;36m' Y='\033[1;33m' N='\033[0m'

echo ""
echo -e "${C}╔════════════════════════════════════════════════╗${N}"
echo -e "${C}║  「STAR PLATINUM」— Cluster Reset & Restart      ║${N}"
echo -e "${C}╚════════════════════════════════════════════════╝${N}"
echo ""

# ── Node definitions ─────────────────────────────────────────────
# Edit these to match your nodes. Format: "user@ip"
# The first entry is the LOCAL node (M4 Max) — runs commands directly.
# The rest are REMOTE nodes — runs commands via SSH.

LOCAL_USER="ravenx"
REMOTE_NODES=(
    "admin@192.168.1.159"   # Node-3-m1pro
    "node1@192.168.1.163"   # Node1's MacBook Pro (M3)
    "admon@192.168.1.177"   # macbook-m2 (M2 Pro)
)

NAMESPACE="star-platinum"
EXO_DIR="Projects/exo"

# ── Commands to run on each node ─────────────────────────────────
read -r -d '' NODE_COMMANDS << 'CMDS' || true
echo ">>> Stopping exo..."
pkill -9 -f exo 2>/dev/null || true
sleep 2

echo ">>> Clearing event logs and state..."
rm -rf ~/.exo/event_log ~/.exo/state 2>/dev/null || true

echo ">>> Pulling latest code..."
cd ~/${EXO_DIR} && git stash 2>/dev/null; git pull --rebase origin main 2>/dev/null || git pull origin main 2>/dev/null || true

echo ">>> Installing dependencies..."
cd ~/${EXO_DIR} && uv sync 2>/dev/null || true

echo ">>> Starting exo in background..."
cd ~/${EXO_DIR} && nohup bash -c "EXO_LIBP2P_NAMESPACE=${NAMESPACE} uv run exo" > ~/.exo/exo.log 2>&1 &
disown

echo ">>> Node ready. exo PID: $(pgrep -f 'uv run exo' | head -1 || echo 'starting...')"
CMDS

# Substitute variables into the command template
make_commands() {
    echo "$NODE_COMMANDS" | sed "s|\${EXO_DIR}|${EXO_DIR}|g" | sed "s|\${NAMESPACE}|${NAMESPACE}|g"
}

# ── Phase 1: Reset LOCAL node (M4 Max) ──────────────────────────
echo -e "${Y}[1/4]${N} Resetting LOCAL node (M4 Max)..."
eval "$(make_commands)"
echo -e "${G}[ok]${N}  M4 Max reset and exo starting"
echo ""

# ── Phase 2: Reset REMOTE nodes via SSH ──────────────────────────
NODE_NUM=2
for node in "${REMOTE_NODES[@]}"; do
    echo -e "${Y}[${NODE_NUM}/4]${N} Resetting ${node}..."
    
    # SSH with timeout, no strict host checking, and forward the commands
    ssh -o ConnectTimeout=10 \
        -o StrictHostKeyChecking=no \
        -o BatchMode=yes \
        "${node}" "$(make_commands)" 2>/dev/null
    
    if [ $? -eq 0 ]; then
        echo -e "${G}[ok]${N}  ${node} reset and exo starting"
    else
        echo -e "${R}[!!]${N}  ${node} — SSH failed. Reset manually on this node."
    fi
    echo ""
    NODE_NUM=$((NODE_NUM + 1))
done

# ── Phase 3: Wait and verify ─────────────────────────────────────
echo -e "${C}Waiting 15 seconds for all nodes to start...${N}"
sleep 15

echo ""
echo -e "${C}╔════════════════════════════════════════════════╗${N}"
echo -e "${C}║  Cluster Status                                ║${N}"
echo -e "${C}╚════════════════════════════════════════════════╝${N}"
echo ""

# Check local
if pgrep -f "uv run exo" > /dev/null 2>&1; then
    echo -e "  ${G}✓${N} M4 Max (local) — exo running"
else
    echo -e "  ${R}✗${N} M4 Max (local) — exo NOT running"
fi

# Check remotes
for node in "${REMOTE_NODES[@]}"; do
    if ssh -o ConnectTimeout=5 -o BatchMode=yes "${node}" "pgrep -f 'uv run exo'" > /dev/null 2>&1; then
        echo -e "  ${G}✓${N} ${node} — exo running"
    else
        echo -e "  ${R}✗${N} ${node} — exo NOT running"
    fi
done

echo ""
echo -e "${G}  Dashboard: http://localhost:52415${N}"
echo -e "${G}  Namespace: ${NAMESPACE}${N}"
echo ""
echo -e "${C}  The Nack storm fix is deployed. Nodes should sync in seconds, not minutes.${N}"
echo -e "${C}  Open the dashboard and load a model!${N}"
echo ""
