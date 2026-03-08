# STAR PLATINUM CLUSTER

Local-first AI cluster orchestration for RavenX.

## Mission
- Keep **Qwen local as core brain**
- Route heavy/complex tasks to hosted models
- Add ANE acceleration/training tier via `DeadByDawn101/ANE`
- Prepare TB4 transport layer for high-speed data movement

## v0 Components
- `services/scheduler`: policy router (local Qwen -> hosted fallback)
- `services/ane_worker`: ANE job wrapper (compile/eval/train hooks)
- `configs/routing.yaml`: model/resource routing policy
- `docs/ARCHITECTURE.md`: cluster topology + rollout plan

## Quick start
```bash
python3 services/scheduler/main.py
python3 services/ane_worker/main.py
```

## Priority roadmap
1. Qwen local core (14b now, 72b once downloaded)
2. Hosted fallback mesh (Sonnet, Codex, Grok, Gemini, MiniMax)
3. ANE worker integration with compile cache
4. TB4 data plane shim (checkpoint/batch movement)
5. Unified metrics + failover controller
