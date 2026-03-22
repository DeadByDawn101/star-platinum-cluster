#!/usr/bin/env bash
# Usage: ./scripts/deploy_agent.sh <user@host> <node_id> <role> [caps]
# Example: ./scripts/deploy_agent.sh admon@macbook-m2.local macbook-m2 ane-worker ane
set -euo pipefail

REMOTE="$1"
NODE_ID="${2:-worker}"
ROLE="${3:-ane-worker}"
CAPS="${4:-ane}"
BRAIN_HOST="${BRAIN_HOST:-192.168.1.151}"
NODE_PORT="${NODE_PORT:-9091}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[deploy] Pushing node agent to $REMOTE ($NODE_ID / $ROLE)"
ssh "$REMOTE" "mkdir -p ~/star-platinum-worker"
scp "$SCRIPT_DIR/services/node_agent/main.py" "$REMOTE:~/star-platinum-worker/node_agent.py"

ssh "$REMOTE" "
  pkill -f node_agent.py 2>/dev/null || true
  sleep 1
  SPC_BRAIN_HOST=$BRAIN_HOST SPC_NODE_ID=$NODE_ID SPC_NODE_ROLE=$ROLE SPC_CAPS=$CAPS SPC_NODE_PORT=$NODE_PORT \
    nohup python3 -u ~/star-platinum-worker/node_agent.py >> ~/star-platinum-worker/agent.log 2>&1 &
  echo \$! > ~/star-platinum-worker/agent.pid
  sleep 3
  curl -s http://127.0.0.1:$NODE_PORT/health
"
echo "[deploy] Done — $NODE_ID online"
