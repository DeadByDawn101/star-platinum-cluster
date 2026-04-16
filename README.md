# STAR PLATINUM CLUSTER

**RavenX Supercomputer** — a dual-brain Apple Silicon + CUDA compute fabric.
RDMA over Thunderbolt, Apple Neural Engine direct compute, DirectReduce offload, and an optional NVIDIA sidecar for CUDA-native workloads.

Built from consumer Apple hardware with a Thunderbolt 5 eGPU extension for CUDA inference. Local-first. No cloud.

---

## Fleet

| # | Node | Chip | Memory | Cores (CPU / GPU / ANE) | Role |
|---|------|------|--------|------------------------|------|
| 1 | **Mac Studio** | Apple M3 Ultra | 96 GB | 28 / 60 / 32 | **Brain A** — OpenClaw, scheduler, orchestration (headless) |
| 2 | **MBP 14"** | Apple M4 Max | 128 GB | 16 / 40 / 16 | **Brain B** — heavy inference, training (headless) |
| 3 | **MacBook** | Apple M3 | 24 GB | 8 / 10 / 16 | Worker — pipeline parallel, model cache |
| 4 | **Mac Studio** (incoming) | Apple M4 Max | 36 GB | 14 / 32 / 16 | Worker — ANE node, tensor parallel shard |
| 5 | **Sonnet Breakaway Box** (incoming) | NVIDIA RTX 3090 | 24 GB VRAM | — / — / — | **CUDA sidecar** — vLLM/exllama, fine-tuning |
| 6 | **Mac Pro 2013** (Linux) | Xeon E5-1680 v2 | 64 GB | 8 / — / — | File server — storage, Docker services, `rdma-core` userspace (Tailscale + 4× TB3, not on TB ring) |
| 7 | **M2 Air** | Apple M2 | 16 GB | 10 / 10 / 16 | Remote SSH access + OpenClaw client |

**Retired:** M1 Pro MBP, M2 Pro MBP, iMac Pro 2017 — sold to fund cluster expansion (more 3090s or an RTX 5090).

### Compute totals (5-node Apple ring + CUDA sidecar)

| Resource | Total | Notes |
|---|---|---|
| Unified memory (Apple) | **284 GB** | Across M3 Ultra, M4 Max 128, M3 24, M4 Max 36 |
| CUDA VRAM | **24 GB** | RTX 3090 |
| ANE | **~80 TFLOPS FP16** | M3 Ultra (32-core) + 4× M-series ANE |
| Apple GPU | **~90 TFLOPS FP16** | Combined Metal across ring |
| CUDA | **~35 TFLOPS FP16** | 3090 (native CUDA, Flash Attention 3 ready) |
| **Combined compute** | **~205 TFLOPS FP16** | Heterogeneous — scheduled by device class |

---

## Physical topology

```
                           TB5 (120G) ──────► TB4 (40G)

              ┌──────────────────────┐
              │   M3 Ultra (Brain A) │       ◄── 6× TB5 ports, hub
              │   96GB · 32-ANE      │           OpenClaw lives here
              │   60-GPU · 20P+8E CPU│
              └──────┬───┬────┬──────┘
                     │   │    │
          TB5─TB4    │   │    │   TB5─TB4
          120G       │   │    │   120G
         ┌───────────┘   │    └────────────┐
         │               │                 │
         ▼               ▼                 ▼
  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
  │ M4 Max 128  │  │ M4 Max 36   │  │   M3 24GB   │
  │ (Brain B)   │  │ (worker)    │  │  (worker)   │
  │ 40-GPU 16T  │  │ 32-GPU 16T  │  │ 10-GPU 16T  │
  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘
         │                │                │
         └────────TB4 ring (40G) ──────────┘

  ─── CUDA sidecar (TB5, off-ring) ────────────────────────

         M3 Ultra ──TB5 80Gbps──► Sonnet Breakaway 850 T5
                                  └─► RTX 3090 24GB VRAM
                                      (Tiny Corp driver, CUDA compute only)

  ─── Ethernet / Tailscale (out of band) ──────────────────

         Beast (Mac Pro 2013, 64GB, 10GbE)    — file server, Docker
         M2 Air                               — remote SSH
```

**Ring:** 4-node Apple Silicon RDMA over Thunderbolt (M3 Ultra ↔ M4 Max 128 ↔ M4 Max 36 ↔ M3 24 ↔ M3 Ultra).
**Sidecar:** 3090 attached to M3 Ultra via TB5 (80 Gbps), CUDA-only, off-ring.
**Out-of-band:** Beast (storage) and M2 Air (remote) on Tailscale/Ethernet, not on TB ring.

---

## Dual-brain design

Star Platinum runs **two coordinated brains** instead of a single scheduler:

| Brain | Chip | Responsibility |
|---|---|---|
| **Brain A** (M3 Ultra) | OpenClaw runtime, agent orchestration, routing policy, session state, memory, skills | Always-on. Light compute. Scheduler. |
| **Brain B** (M4 Max 128) | Heavy model inference, training, prefill, long-context reasoning | Invoked by Brain A when a task needs muscle. |

**Why split it:**
- OpenClaw needs low-latency, always-on orchestration — that's the Studio's job.
- Heavy inference monopolizes memory/compute — you don't want the orchestrator stalling behind a 70B generate.
- The M4 Max 128 can fully commit to a big model (70B Q4 fits with room); the Studio never hangs.

**Hand-off:** Brain A makes routing decisions. For anything above a size threshold (configurable, default 8B), Brain A dispatches to Brain B via exo. Smaller/faster models and tool-use loops run on Brain A directly.

---

## Software stack

| Layer | Component | What it does |
|---|---|---|
| L6 | **OpenClaw** | Agent runtime on Brain A — skills, sessions, routing, memory |
| L5 | **exo** | Distributed scheduler — auto-discovery, topology-aware placement, tensor/pipeline parallel, OpenAI/Claude/Ollama API |
| L4 | **Device routing** | Classifies jobs by device class: ANE / Metal / CUDA / CPU. See `configs/routing.yaml` |
| L4a | **ANE compute** | 16–32 TFLOPS/node via `_ANEClient` private APIs |
| L4b | **CUDA backend** | 3090 via Tiny Corp driver (Apple-approved, no SIP disable) — vLLM, exllama, Flash Attention 3 |
| L3 | **DirectReduce** | Offloaded all-reduce at ANE background QoS — GateKeeper / DataDirector / ComputeEnhancer |
| L3a | **TurboQuant-MLX** | KV cache compression (2.8× at 4-bit, near-lossless) |
| L3b | **Grove-MLX** | Distributed training with autoresearch parameter discovery |
| L2 | **Zero-copy memory** | IOSurface-backed pinned regions on Mac / `ibv_reg_mr` on Linux |
| L1 | **OdinLink + exo RDMA** | TB4/TB5 DMA ring transport, RCCL Net v7 plugin |
| L0 | **Hardware** | M3 Ultra + M4 Max ANE/GPU/unified memory; RTX 3090 via TB5 eGPU |

---

## Device routing (new)

With the 3090 in the fleet, Star Platinum now schedules by **device class** rather than node-uniform placement.

```yaml
# configs/routing.yaml (sketch)
classes:
  ane:
    nodes: [m3-ultra, m4-max-128, m4-max-36, m3-24]
    workloads: [prefill, reduction, small-model-inference]
  metal:
    nodes: [m3-ultra, m4-max-128, m4-max-36, m3-24]
    workloads: [mlx-inference, fine-tune-lora]
  cuda:
    nodes: [rtx-3090]
    workloads: [vllm-serving, flash-attn-3, exllama, fine-tune-qlora]
    preferred_models: [*-gguf, *-awq, *-gptq]
  cpu:
    nodes: [beast]
    workloads: [embedding, rerank, storage]

routing:
  default: metal
  rules:
    - when: model.format in [gguf, awq, gptq, safetensors-pytorch]
      route: cuda
    - when: model.format == mlx
      route: metal
    - when: task == "all-reduce"
      route: ane
```

---

## Roadmap

| Phase | Status | Description |
|---|---|---|
| 1. exo cluster bringup | ✅ done | exo on all ring nodes, TB RDMA, 4-node ring verified |
| 2. ANE compute backend | ✅ done | ANE dispatch wired into exo runner |
| 3. DirectReduce v1 | ✅ done | ANE-accelerated gradient reduction at background QoS |
| 4. Dual-brain split | 🚧 in progress | OpenClaw on M3 Ultra, heavy inference on M4 Max 128 |
| 5. **M4 Max 36 onboarding** | 📦 hardware incoming | Slot into ring as 5th Apple node, update exo/TurboQuant configs |
| 6. **3090 CUDA sidecar** | 📦 hardware incoming | Tiny Corp driver install, vLLM/exllama setup, device-class router |
| 7. Unified training | ⏳ planned | Distributed forward/backward across ANE ring + CUDA sidecar |
| 8. Hardening | ⏳ planned | Metrics, failover, monitoring dashboard |
| 9. Public release | ⏳ planned | Docs, benchmarks, packaging |

---

## TurboQuant + Grove integration

Star Platinum integrates [TurboQuant-MLX](https://github.com/DeadByDawn101/turboquant-mlx) (KV cache compression) and [Grove-MLX](https://github.com/DeadByDawn101/grove-mlx) (distributed training with autoresearch).

**TurboQuant KV compression:**

| Bits | Cosine sim | Compression | Use case |
|---|---|---|---|
| 4-bit | 0.9939 | 2.8× | Production inference (recommended) |
| 3-bit | 0.9723 | 2.8× | Memory-constrained |
| 2-bit | 0.8572 | 2.8× | Extreme compression |

Features: polar coordinate quantization, QJL residual correction, FP16 attention sinks (first 128 tokens uncompressed), persistent KV cache (135× faster than reprocessing — 7.5ms load vs 1010ms recompute).

**Grove autoresearch (2026-03-26 winner):** `wifi-raw` — chunk_size=4096, topk=64, use_dct=False, H=200. 5933 MB/s with 31.2× compression on mixed TB4/WiFi topology.

See `configs/turboquant_config.json` for production config.

---

## Repository structure

```
star-platinum-cluster/
├── configs/
│   ├── routing.yaml              # Device-class routing policy (NEW)
│   ├── supercomputer.yaml        # Full cluster config
│   └── turboquant_config.json    # KV compression settings
├── docs/
│   ├── ARCHITECTURE.md           # Cluster topology + rollout
│   ├── HARDWARE-REGISTRY.md      # Exact specs for every node
│   ├── DUAL-BRAIN.md             # Brain A / Brain B split (NEW)
│   ├── CUDA-SIDECAR.md           # 3090 + Tiny Corp setup (NEW)
│   ├── DIRECTREDUCE-ADAPTATION.md
│   ├── CLUSTER-BRINGUP.md
│   └── NODE-ONBOARDING.md
├── services/
│   ├── scheduler/main.py         # Legacy (replaced by exo)
│   ├── ane_engine/ane_compute.py # ANE backend for exo
│   ├── cuda_engine/              # CUDA sidecar backend (NEW)
│   ├── directreduce/main_v1.py   # ANE-accelerated all-reduce
│   └── openclaw/                 # Brain A runtime (NEW)
└── scripts/
    ├── cluster_up.sh
    ├── cluster_down.sh
    ├── cluster_health.sh
    ├── cuda_sidecar_bringup.sh   # Tiny Corp driver + vLLM (NEW)
    └── benchmark_directreduce.py
```

---

## Quick start

```bash
# Start exo on every ring node
uv run exo    # http://localhost:52415

# Bring up Brain A (OpenClaw) on M3 Ultra
./scripts/cluster_up.sh

# Health check the full fleet
./scripts/cluster_health.sh

# Bring up the 3090 CUDA sidecar (when hardware arrives)
./scripts/cuda_sidecar_bringup.sh
```

---

## Companion repositories

| Repo | Purpose |
|---|---|
| [exo](https://github.com/DeadByDawn101/exo) | Distributed AI scheduler with RDMA over Thunderbolt |
| [OdinLink-Five](https://github.com/DeadByDawn101/OdinLink-Five) | TB4/TB5 DMA ring driver + RCCL plugin |
| [ANE](https://github.com/DeadByDawn101/ANE) | Apple Neural Engine direct compute + training |
| [turboquant-mlx](https://github.com/DeadByDawn101/turboquant-mlx) | KV cache compression for Apple Silicon |
| [grove-mlx](https://github.com/DeadByDawn101/grove-mlx) | Distributed training with autoresearch |
| [rdma-core](https://github.com/DeadByDawn101/rdma-core) | Linux RDMA userspace (reference) |

---

## References

- DirectReduce: A Scalable Ring AllReduce Offloading Architecture for Torus Topologies (IEEE IoT Journal, 2025)
- Inside the M4 Apple Neural Engine (maderix, 2026)
- TurboQuant: Cost-Effective KV-Cache Compression (arXiv, 2025)
- PolarQuant: Rotation-Based KV Cache Quantization (arXiv, 2025)
- Tiny Corp eGPU driver for Apple Silicon (Apple-approved, April 2026)

---

**Built with 🖤 by [RavenX AI](https://github.com/DeadByDawn101)**
