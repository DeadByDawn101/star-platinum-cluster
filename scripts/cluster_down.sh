#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_DIR="$ROOT_DIR/.run/pids"

stop_one() {
  local name="$1"
  local pidfile="$PID_DIR/${name}.pid"
  if [[ ! -f "$pidfile" ]]; then
    echo "[skip] $name pid file not found"
    return
  fi

  local pid
  pid="$(cat "$pidfile")"
  if kill -0 "$pid" 2>/dev/null; then
    echo "[stop] $name (pid $pid)"
    kill "$pid" || true
  else
    echo "[skip] $name not running"
  fi
  rm -f "$pidfile"
}

stop_one scheduler
stop_one directreduce
stop_one ane_worker

echo "Cluster services stopped."
