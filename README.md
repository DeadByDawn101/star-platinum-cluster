# STAR PLATINUM CLUSTER

Local-first AI cluster orchestration for RavenX.

## Mission
- Keep **Qwen local as core brain**
- Route heavy/complex tasks to hosted models
- Add ANE acceleration/training tier via `DeadByDawn101/ANE`
- Prepare TB4 transport layer for high-speed data movement

## v0 Components
- `services/scheduler`: policy router (local Qwen -> directreduce/ANE -> hosted fallback)
- `services/ane_worker`: ANE job wrapper (compile/eval/train hooks)
- `services/directreduce`: all-reduce offload service (software v0)
- `configs/routing.yaml`: model/resource routing policy
- `docs/ARCHITECTURE.md`: cluster topology + rollout plan
- `docs/DIRECTREDUCE-ADAPTATION.md`: deep-dive + application of DirectReduce paper

## Quick start
```bash
# start all local services
./scripts/cluster_up.sh

# check health
./scripts/cluster_health.sh

# benchmark directreduce path
python3 scripts/benchmark_directreduce.py

# stop all services
./scripts/cluster_down.sh
```

### SOUL mode core-model override
Use this when running SOUL-enhanced local default (gpt-oss-20b-heretic):
```bash
export SPC_CORE_MODEL="ollama/gpt-oss-20b-heretic"
./scripts/cluster_up.sh
```

### Route check example
```bash
curl -s http://127.0.0.1:9090/route \
  -H "content-type: application/json" \
  -d '{"task_type":"high_reasoning","payload":{}}' | jq
```

## Priority roadmap
1. Qwen local core (14b now, 72b once downloaded)
2. Hosted fallback mesh (Sonnet, Codex, Grok, Gemini, MiniMax)
3. ANE worker integration with compile cache
4. TB4 data plane shim (checkpoint/batch movement)
5. Unified metrics + failover controller

## Cluster registry API
- `GET /health`
- `GET /nodes`
- `POST /nodes/register`
- `POST /route`

See `docs/NODE-ONBOARDING.md` for one-by-one node registration flow.
Heretic local setup: `docs/HERETIC-SETUP.md`.
