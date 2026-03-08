# DirectReduce Adaptation Plan for STAR PLATINUM CLUSTER

Reference paper: **DirectReduce: A Scalable Ring AllReduce Offloading Architecture for Torus Topologies** (IEEE IoT Journal, 2025, DOI: 10.1109/JIOT.2025.3584768)

## Why this matters for our cluster
Our cluster needs faster gradient/state sync without stalling core compute on local Qwen + ANE nodes.
DirectReduce's key insight applies directly:
- Stop interrupting main compute (Qwen/ANE workers)
- Offload intermediate reductions to transport-side workers
- Return only final reduced shards to compute nodes

## Paper summary (actionable)
DirectReduce proposes 3 components:
1. **GateKeeper**: routes outgoing chunks either to packetization or immediate reduction pipeline
2. **DataDirector**: classifies incoming chunks as intermediate-vs-final
3. **ComputeEnhancer**: executes reduction ops (sum/max/etc.) on the NIC/offload path

Reported gains: up to ~1.98x latency reduction for ring all-reduce in torus-style setups.

## RavenX adaptation (software-first, then TB4-enhanced)

### Phase 1 (now): Software DirectReduce overlay
- Implement DirectReduce semantics in user-space services over TB4/Ethernet transport.
- Keep reduction off main model workers.
- Support reduce ops: `sum`, `max`, `mean`.

### Phase 2: TB4 data-plane acceleration
- Move chunk transfer to TB4 high-throughput links.
- Add zero-copy shared-memory buffers between reducer and scheduler.

### Phase 3: SmartNIC / kernel offload hooks
- Abstract reducer backend so hardware offload can replace software reducer later.
- Prepare RDMA-like queue semantics once TB4 transport matures.

## Component mapping to our repo
- **GateKeeper** -> `services/directreduce/gatekeeper.py`
- **DataDirector** -> `services/directreduce/datadirector.py`
- **ComputeEnhancer** -> `services/directreduce/compute_enhancer.py`
- Orchestration API -> `services/directreduce/main.py`

## Integration points
1. Scheduler sends all-reduce jobs to `directreduce` for eligible workloads.
2. ANE worker and Qwen worker publish partial tensors/chunks.
3. DirectReduce service aggregates + returns final chunks only.
4. Scheduler routes final output back into training/inference loop.

## Initial KPI targets
- 25-35% all-reduce latency cut in 2-node tests
- 40%+ host CPU interruption reduction during sync steps
- Stable correctness parity with baseline all-reduce

## Risks
- No true SmartNIC offload yet (software emulation first)
- TB4 transport jitter/hotplug handling required
- Chunk sizing and backpressure need tuning

## Next implementation tasks
1. Build v0 DirectReduce service skeleton (done in this repo)
2. Wire scheduler path `task_type=all_reduce` -> directreduce
3. Add benchmark harness baseline-vs-directreduce
4. Add correctness tests (sum/max/mean) with deterministic fixtures
