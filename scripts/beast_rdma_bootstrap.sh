#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${BEAST_HOST:-}" ]]; then
  echo "Set BEAST_HOST=user@host"
  exit 1
fi

ssh "$BEAST_HOST" 'bash -s' <<'REMOTE'
set -euo pipefail
sudo apt update
sudo apt install -y rdma-core ibverbs-providers librdmacm1 libibverbs1 ibverbs-utils perftest
rdma link show || true
ibv_devices || true
ibv_devinfo || true
REMOTE

echo "Beast RDMA bootstrap complete for $BEAST_HOST"
