# STAR PLATINUM CLUSTER

> RavenX Supercomputer — RDMA + ANE + DirectReduce unified compute fabric.

The first local-first AI supercomputer built from consumer Apple hardware. Unifies RDMA over Thunderbolt, Apple Neural Engine direct compute, and offloaded all-reduce into a distributed training and inference platform.

## Cluster hardware

| Node | Chip | Memory | ANE TFLOPS | GPU TFLOPS | TB | Storage | Role |
|------|------|--------|-----------|-----------|-----|---------|------|
| **M4 Max** MBP 14" | Apple M4 Max | 128 GB | 19.0 | ~54 | 3×TB5 (120G) | 1 TB | Brain — scheduler, core model, primary compute |
| **M1 Pro** MBP 16" | Apple M1 Pro | 16 GB | 11.0 | ~5 | 3×TB4 (40G) | 500 GB | ANE compute — ring hop 2, 11T ANE |
| **iMac Pro** 2017 | Xeon W-2140B | 32 GB | 0 | ~22 (Vega) | 4×TB3 (40G) | 1 TB | Control plane — dashboard, GPU compute |
| **M2 Pro** MBP 16" | Apple M2 Pro | 16 GB | 7.9 | ~14 | 3×TB4 (40G) | 500 GB | ANE node — tensor parallel shard |
| **M3** MBP 14" | Apple M3 | 24 GB | 9.0 | ~7 | 2×TB4 (40G) | 2 TB | ANE worker — pipeline parallel, model cache |
| **Beast** Mac Pro 2013 | Xeon E5-1680 v2 | 64 GB | 0 | — | TB2 (dead) | 1 TB | Docker host — storage, software services |
| **M2 Air** 2022 | Apple M2 | — | ~7.9 | — | 2×USB4 | — | SSH remote access + OpenClaw |

**Totals (5-node RDMA ring):** 216 GB unified memory | **46.9 ANE TFLOPS** | ~102 GPU TFLOPS FP16

## Physical topology

```
          ┌──────────────────────────────────────────┐
          │             TB5 (120G)                   │
          ▼                TB4 (40G)                 │
  ┌──────────────┐     ──────────────▶    ┌──────────────┐
  │   M4 Max     │ ─────TB5→TB4, 40G────▶ │   M1 Pro     │
  │  (brain)     │                        │  (ane-node)  │
  │  128GB  19T  │ ◀────TB4→TB5, 40G───── │  16GB   11T  │
  └──────┬───────┘                        └──────┬───────┘
         │ TB5→TB4                               │ TB4→TB3
         │  40G (ring close)                     │  40G
         │                               ┌───────▼───────┐
         │                               │   iMac Pro    │
         │                               │  (control)    │
         │                               │  32GB   0T    │
         │                               │  Vega 22T GPU │
         │                               └───────┬───────┘
         │                                       │ TB3→TB4
         │                                       │  40G
  ┌──────▼───────┐                      ┌────────▼──────┐
  │     M3       │ ◀─────TB4, 40G─────── │   M2 Pro     │
  │  (ane-lite)  │                       │  (ane-node)  │
  │  24GB    9T  │                       │  16GB   7.9T │
  └──────────────┘                       └──────────────┘

  Ring: M4 Max → M1 Pro → iMac Pro → M2 Pro → M3 → M4 Max
  All links: 40 Gbps Thunderbolt

  ─── Ethernet / Tailscale (not on TB ring) ───────────────

  ┌─────────────┐          ┌─────────────┐
  │   Beast     │          │   M2 Air    │
  │  (Docker)   │          │   (SSH)     │
  │  64GB 1GbE  │          │  remote     │
  └─────────────┘          └─────────────┘
```

4-node RDMA ring via Thunderbolt. Beast on Ethernet/Tailscale for Docker services and storage. M2 Air for remote SSH access.

## Software stack

| Layer | Component | What it does |
|-------|-----------|-------------|
| L5 | **[exo](https://github.com/DeadByDawn101/exo)** | Cluster scheduler — auto-discovery, topology-aware placement, RDMA ring detection, tensor/pipeline parallel, OpenAI/Claude/Ollama API |
| L4 | **[ANE](https://github.com/DeadByDawn101/ANE)** compute | 19 TFLOPS/node via `_ANEClient` private APIs — prefill at real-time QoS, reduction at background QoS |
| L3 | **DirectReduce** | Offloaded all-reduce — GateKeeper/DataDirector/ComputeEnhancer with ANE hardware acceleration |
| L2 | Zero-copy memory | IOSurface-backed pinned regions (Mac) / `ibv_reg_mr` pattern — DMA-ready tensors |
| L1 | **[OdinLink](https://github.com/DeadByDawn101/OdinLink-Five)** + exo RDMA | TB4/TB5 DMA ring transport — 40-120 Gbps, zero-copy, RCCL Net v7 plugin |
| L0 | Hardware | Apple Silicon ANE + GPU + unified memory across Thunderbolt |

## Key integrations

### ANE as cluster TFLOPS multiplier

The ANE is not just for training — it is a 19 TFLOPS FP16 graph execution engine per node. At 32+ chained operations, ANE reaches 94% utilization. The cluster uses ANE for:
- **Inference prefill** at real-time QoS (high throughput, batched)
- **Gradient reduction** at background QoS (DirectReduce ComputeEnhancer)
- **On-device training** via dynamic weight pipeline (weights in IOSurface spatial dims)

ANE supports a 127-deep evaluation queue, enabling simultaneous inference + reduction on the same chip.

### DirectReduce (IEEE IoT Journal 2025)

Software implementation of [DirectReduce: A Scalable Ring AllReduce Offloading Architecture for Torus Topologies](https://ieeexplore.ieee.org/document/11062587). Three-stage pipeline:
- **GateKeeper**: routes chunks to reduction vs. packetization path
- **DataDirector**: classifies incoming chunks as intermediate vs. final
- **ComputeEnhancer**: executes reduction ops on ANE background queue

Up to 1.98x all-reduce latency reduction in ring topologies.

### exo scheduler

Replaces the original custom scheduler with [exo](https://github.com/DeadByDawn101/exo) production-grade orchestration:
- Automatic mDNS device discovery via libp2p
- Topology-aware model placement with RDMA cycle detection
- Tensor parallel (1.8x on 2 devices, 3.2x on 4 devices)
- Pipeline parallel with memory-proportional layer allocation
- Master election via distributed consensus

## Repository structure

```
star-platinum-cluster/
├── configs/
│   ├── routing.yaml              # Model/resource routing policy
│   └── supercomputer.yaml        # Full cluster config (all nodes, all layers)
├── docs/
│   ├── ARCHITECTURE.md           # Cluster topology + rollout plan
│   ├── HARDWARE-REGISTRY.md      # Exact specs for every node
│   ├── DIRECTREDUCE-ADAPTATION.md # DirectReduce paper application
│   ├── CLUSTER-BRINGUP.md        # Step-by-step cluster startup
│   ├── NODE-ONBOARDING.md        # Node registration flow
│   ├── HERETIC-SETUP.md          # Local gpt-oss-20b-heretic worker
│   ├── LINUX-RDMA-BEAST.md       # Beast Linux integration
│   └── REPO-INTEL.md             # External repo scan
├── services/
│   ├── scheduler/main.py         # Policy router (legacy, replaced by exo)
│   ├── ane_worker/main.py        # ANE job wrapper
│   ├── ane_engine/ane_compute.py  # ANE compute backend for exo integration
│   ├── directreduce/main.py      # All-reduce v0 (software)
│   ├── directreduce/main_v1.py   # All-reduce v1 (ANE-accelerated)
│   └── heretic_worker/main.py    # gpt-oss-20b-heretic local model
└── scripts/
    ├── cluster_up.sh             # Start all local services
    ├── cluster_down.sh           # Stop all services
    ├── cluster_health.sh         # Health check
    ├── beast_rdma_bootstrap.sh   # Beast RDMA setup
    └── benchmark_directreduce.py # Correctness/perf harness
```

## Quick start

```bash
# Start legacy local services (scheduler + directreduce + ane_worker)
./scripts/cluster_up.sh

# Health check
./scripts/cluster_health.sh

# Benchmark DirectReduce v1 (ANE-accelerated when available)
python3 services/directreduce/main_v1.py &
python3 scripts/benchmark_directreduce.py

# Start exo on each node (replaces legacy scheduler)
uv run exo  # runs at http://localhost:52415
```

## Companion repositories

| Repo | Purpose |
|------|---------|
| [exo](https://github.com/DeadByDawn101/exo) | Distributed AI scheduler with RDMA over Thunderbolt |
| [OdinLink-Five](https://github.com/DeadByDawn101/OdinLink-Five) | TB4/TB5 DMA ring driver + RCCL plugin |
| [ANE](https://github.com/DeadByDawn101/ANE) | Apple Neural Engine direct compute + training |
| [rdma-core](https://github.com/DeadByDawn101/rdma-core) | Linux RDMA userspace stack (Beast node reference) |

## Roadmap

1. **Phase 1** — exo cluster bringup: install exo on all ring nodes, configure TB RDMA, verify 4-node ring
2. **Phase 2** — ANE compute backend: wire ANE dispatch into exo runner protocol
3. **Phase 3** — DirectReduce v1: ANE-accelerated gradient reduction at background QoS
4. **Phase 4** — Unified training: distributed forward/backward across ANE ring with DirectReduce sync
5. **Phase 5** — Hardening: metrics, failover, monitoring dashboard
6. **Phase 6** — Public release: documentation, benchmarks, packaging

## References

- [DirectReduce: A Scalable Ring AllReduce Offloading Architecture for Torus Topologies](https://ieeexplore.ieee.org/document/11062587) (IEEE IoT Journal, 2025)
- [Inside the M4 Apple Neural Engine](https://maderix.substack.com/p/inside-the-m4-apple-neural-engine) (maderix, 2026)
- [AppleNeuralEngine.framework Runtime Headers](https://github.com/nst/iOS-Runtime-Headers/tree/master/PrivateFrameworks/AppleNeuralEngine.framework)
