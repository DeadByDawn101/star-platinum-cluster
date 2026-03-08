#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/.run/logs"
PID_DIR="$ROOT_DIR/.run/pids"
mkdir -p "$LOG_DIR" "$PID_DIR"

start_service() {
  local name="$1"
  local cmd="$2"
  local log="$LOG_DIR/${name}.log"
  local pidfile="$PID_DIR/${name}.pid"

  if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    echo "[skip] $name already running (pid $(cat "$pidfile"))"
    return
  fi

  echo "[start] $name"
  nohup bash -lc "cd '$ROOT_DIR' && $cmd" >"$log" 2>&1 &
  echo $! > "$pidfile"
}

start_service ane_worker "python3 services/ane_worker/main.py"
start_service directreduce "python3 services/directreduce/main.py"
start_service scheduler "python3 services/scheduler/main.py"

echo ""
echo "Cluster services started."
echo "Logs: $LOG_DIR"
echo "PIDs: $PID_DIR"
