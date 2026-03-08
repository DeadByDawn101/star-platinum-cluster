# Node Onboarding (1-by-1)

This flow brings nodes into scheduler control one at a time.

## 1) Mothership up
```bash
cd ~/Projects/star-platinum-cluster
./scripts/cluster_up.sh
./scripts/cluster_health.sh
```

## 2) Register Beast (Linux RDMA)
```bash
curl -s http://127.0.0.1:9090/nodes/register \
  -H 'content-type: application/json' \
  -d '{
    "node_id":"beast-linux",
    "role":"rdma-worker",
    "host":"BEAST_IP_OR_DNS",
    "port":9092,
    "capabilities":["rdma","allreduce"],
    "status":"online"
  }'
```

## 3) Register Mac Node 1 (ANE)
```bash
curl -s http://127.0.0.1:9090/nodes/register \
  -H 'content-type: application/json' \
  -d '{
    "node_id":"mac-node-1",
    "role":"ane-worker",
    "host":"MAC_NODE_1_IP_OR_DNS",
    "port":9091,
    "capabilities":["ane","train"],
    "status":"online"
  }'
```

## 4) Register Mac Node 2 (ANE)
```bash
curl -s http://127.0.0.1:9090/nodes/register \
  -H 'content-type: application/json' \
  -d '{
    "node_id":"mac-node-2",
    "role":"ane-worker",
    "host":"MAC_NODE_2_IP_OR_DNS",
    "port":9091,
    "capabilities":["ane","train"],
    "status":"online"
  }'
```

## 5) Verify active registry
```bash
curl -s http://127.0.0.1:9090/nodes | jq
```

## 6) Route tests
### All-reduce should prefer beast when RDMA node is online
```bash
curl -s http://127.0.0.1:9090/route \
  -H 'content-type: application/json' \
  -d '{"task_type":"all_reduce","payload":{}}' | jq
```

### ANE jobs should prefer registered ANE nodes
```bash
curl -s http://127.0.0.1:9090/route \
  -H 'content-type: application/json' \
  -d '{"task_type":"embedding_train","payload":{}}' | jq
```
