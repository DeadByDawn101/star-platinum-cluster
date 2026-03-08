#!/usr/bin/env bash
set -euo pipefail

check_http() {
  local name="$1"
  local url="$2"
  if curl -fsS "$url" >/tmp/${name}_health.json 2>/dev/null; then
    echo "[ok] $name: $(cat /tmp/${name}_health.json)"
  else
    echo "[fail] $name: $url unreachable"
  fi
}

echo "== Local cluster health =="
check_http scheduler "http://127.0.0.1:9090/health"
check_http ane_worker "http://127.0.0.1:9091/health"
check_http directreduce "http://127.0.0.1:9092/health"

echo "\n== Optional Beast RDMA health =="
if [[ -n "${BEAST_HOST:-}" ]]; then
  ssh "${BEAST_HOST}" 'command -v rdma >/dev/null && rdma link show || echo "rdma tool not installed"' || true
else
  echo "Set BEAST_HOST=user@host to run remote RDMA checks"
fi
