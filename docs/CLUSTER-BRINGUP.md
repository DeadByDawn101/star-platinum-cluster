# STAR PLATINUM — Cluster Bring-Up Runbook

## 1) Mothership (this Mac)
```bash
cd ~/Projects/star-platinum-cluster
./scripts/cluster_up.sh
./scripts/cluster_health.sh
```

Expected healthy ports:
- Scheduler: `127.0.0.1:9090`
- ANE worker: `127.0.0.1:9091`
- DirectReduce: `127.0.0.1:9092`

## 2) SOUL-enhanced mode (local default model override)
```bash
export SPC_CORE_MODEL="ollama/gpt-oss-20b-heretic"
./scripts/cluster_down.sh
./scripts/cluster_up.sh
```

## 3) Beast Linux RDMA prep
On Beast:
```bash
sudo apt update
sudo apt install -y rdma-core ibverbs-providers librdmacm1 libibverbs1 ibverbs-utils perftest
rdma link show
ibv_devices
ibv_devinfo
```

## 4) Check Beast RDMA from mothership
```bash
export BEAST_HOST="user@beast-hostname-or-ip"
./scripts/cluster_health.sh
```

## 5) Basic route tests
```bash
curl -s http://127.0.0.1:9090/route -H 'content-type: application/json' -d '{"task_type":"routine","payload":{}}'
curl -s http://127.0.0.1:9090/route -H 'content-type: application/json' -d '{"task_type":"all_reduce","payload":{}}'
curl -s http://127.0.0.1:9090/route -H 'content-type: application/json' -d '{"task_type":"high_reasoning","payload":{}}'
```

## 6) Shutdown
```bash
./scripts/cluster_down.sh
```
