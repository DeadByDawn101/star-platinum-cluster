# Dual-Brain Architecture

Star Platinum runs **two coordinated brains** rather than a single monolithic scheduler. This document explains the split, the handoff protocol, and the operational rationale.

---

## The problem this solves

A single-brain design collapses orchestration and heavy compute onto one node. That works until the first 70B generate, at which point:

- The scheduler stalls behind the inference job.
- Agent loops (tool calls, memory lookups, routing decisions) block on a task that doesn't need a scheduler at all.
- KV cache for the big model evicts hot orchestration state.
- A single GPU OOM takes the whole cluster offline.

On consumer Apple hardware — where you're memory-bound, not FLOP-bound — this matters more than on a datacenter box. Unified memory means the scheduler and the model literally fight over the same pool.

**The fix:** split "always-on, low-latency, small footprint" from "heavy, bursty, memory-hungry." Run them on different nodes.

---

## Brain A — M3 Ultra (96 GB)

**The orchestrator.** Always on. Never blocks.

| Responsibility | Why it lives here |
|---|---|
| OpenClaw runtime | Needs low-latency wake, persistent session state, skill dispatch |
| Routing decisions | Must stay responsive even when Brain B is busy |
| Memory / RAG lookups | Small models, fast |
| Skill execution | Tool calls, shell, web fetch — lightweight |
| Small-model inference | Anything **< 8B** runs here directly |
| exo scheduler (master) | Coordinates ring placement |

**Why M3 Ultra specifically:**
- **32-core Neural Engine** — the largest ANE in the fleet, ideal for batched embedding and prefill
- **60-core GPU** — enough Metal compute for sub-8B inference locally
- **6× Thunderbolt 5** — the only node with enough ports to act as a ring hub *and* drive the CUDA sidecar
- **819 GB/s memory bandwidth** — tied with Ultra variants for highest in fleet
- **Headless** — no display contention, always-on server posture

Brain A should stay under roughly 40% memory at steady state. Spikes above that mean routing rules need tuning, or a task that should have gone to Brain B didn't.

---

## Brain B — M4 Max 128 GB MBP

**The muscle.** Invoked on demand. Can monopolize its own resources without breaking orchestration.

| Responsibility | Why it lives here |
|---|---|
| Heavy inference (>8B params) | 128 GB unified memory fits 70B at Q4 with room |
| Training / fine-tuning | Doesn't matter if training runs for hours |
| Long-context prefill | Can spend 10s on a 100k-token prefill without blocking anything |
| Model warm-pool | Keeps 2-3 hot models resident between requests |

**Why M4 Max 128 specifically:**
- **128 GB unified memory** — largest memory pool in the fleet; fits the models that don't fit elsewhere
- **40-core GPU** — strongest single-node Metal throughput in the fleet
- **Newer-generation ANE** (M4) — architectural improvements over M3 for specific kernels
- **Headless laptop** — folded lid, driven by Parsec or pure API; treats itself like a server

When Brain B is busy, Brain A continues to serve small-model traffic and orchestration. Users don't see stalls on agent loops because of a slow 70B generate — those paths never touch Brain B.

---

## Handoff protocol

Every inbound request hits Brain A. Brain A classifies it, then either serves it locally or hands off.

### Classification

Brain A tags each request with a **size class** and **task class**:

```yaml
size:
  - tiny:   < 2B params                # always local (Brain A)
  - small:  2B – 8B params             # local (Brain A), unless memory tight
  - medium: 8B – 30B params            # handoff to Brain B
  - large:  30B+ params                # handoff to Brain B, warm-pool preferred

task:
  - chat:         default              # lowest latency lane
  - reason:       <think>-gated        # medium size threshold drops to 4B
  - tool-loop:    agent-driven         # prefer Brain A — tight loop latency matters
  - generate:     long-output          # may chunk + stream
  - prefill:      long-input           # Brain B — benefits from memory headroom
  - train:        fine-tune / SFT      # always Brain B
  - embed:        vector gen           # Brain A (ANE-accelerated, batched)
```

### Decision matrix

|                  | tiny     | small    | medium       | large        |
|------------------|----------|----------|--------------|--------------|
| **chat**         | Brain A  | Brain A  | Brain B      | Brain B      |
| **reason**       | Brain A  | Brain A  | Brain B      | Brain B      |
| **tool-loop**    | Brain A  | Brain A  | Brain B*     | Brain B*     |
| **generate**     | Brain A  | Brain A  | Brain B      | Brain B      |
| **prefill**      | Brain A  | Brain B  | Brain B      | Brain B      |
| **train**        | Brain B  | Brain B  | Brain B      | Ring (exo)   |
| **embed**        | Brain A  | Brain A  | Brain A      | Brain A      |

*Tool-loops with medium/large models pay a handoff penalty per turn. For agents that tool-call 5+ times per task, consider distillation to a small model — the round-trip cost swamps the size advantage.

### Transport

Both brains sit on native **Thunderbolt 5 with RDMA enabled** (M3 Ultra has 6× TB5, M4 Max 128 has 3× TB5). We take advantage of it: brain-to-brain handoff runs **RDMA over Thunderbolt 5** via OdinLink, not HTTP.

```
Brain A (M3 Ultra)                         Brain B (M4 Max 128)
   │                                                  ▲
   │   TB5 direct link (80 Gbps, RDMA, zero-copy)    │
   │   OdinLink DMA channel + exo worker protocol     │
   └──────────────────────────────────────────────────┘
```

**Why RDMA here:**
- Native TB5 + RDMA is already running on the ring — reusing it is effectively free
- Zero-copy DMA into Brain B's unified memory — no serialize/deserialize
- Sub-millisecond handoff latency vs 5–15ms for Tailscale HTTP
- For long prefills (100k+ tokens), you're moving a large prompt tensor; RDMA saves real wall time vs copying through the networking stack twice
- Keeps the whole cluster on one transport model — one thing to tune, one thing to monitor

**Fallback:** HTTP/exo over Tailscale is retained as a **fallback path** when OdinLink reports a link error or the TB5 cable is unplugged. Degraded mode, still functional, just higher latency. Configured in `routing.yaml`:

```yaml
brain_handoff:
  primary: odinlink-rdma
  fallback: http-tailscale
  timeout_ms: 2000
  retry_on_fallback: true
```

**What this doesn't change:** ring RDMA continues to handle tensor-parallel shard traffic and gradient all-reduce across all four Apple Silicon nodes. Brain A → Brain B is now just one more RDMA consumer on the ring. The dual-brain split is still about **which brain is master** — the transport choice is an optimization that falls out of "we already have the fabric, use it."

---

## Failure modes and fallbacks

### Brain B down / unreachable
Brain A's routing rules check Brain B health every 5s. If Brain B is down:
- Medium requests: degrade to Brain A if memory allows, else 503
- Large requests: hard fail, 503 with "heavy inference unavailable"
- Tool-loops and small chat: unaffected

The cluster stays operable for the 80% of traffic that's small.

### Brain A down
OpenClaw itself is down. Full outage. There is no automatic failover to Brain B — the idea is that Brain A is on a Mac Studio that basically never goes down, and if it does something big is wrong.

Manual recovery: SSH to M4 Max 128, start a minimal OpenClaw shim there, update DNS. Documented in `CLUSTER-BRINGUP.md` (recovery section, TBD).

### Brain B OOM during inference
Exo returns an error. Brain A:
1. Doesn't retry blindly (could re-OOM).
2. Drops to next smaller model if the router defines a fallback chain.
3. Otherwise returns the error to the caller with the original request preserved.

### TB link down between brains
If the TB5 cable between M3 Ultra and M4 Max 128 fails or unplugs:
- OdinLink reports link-down via interface event.
- Routing policy auto-falls-back to `http-tailscale` within `timeout_ms` (default 2000ms).
- Brain-to-brain latency degrades but traffic continues.
- Metrics emit a `brain_handoff_transport="fallback"` label so dashboards light up.

### Tailscale partition on top of TB failure
Only a concern in the rare case of *both* the TB5 link failing *and* the Tailscale network being partitioned. In that double-failure scenario:
- Brain A's health check eventually times out, marks Brain B down.
- Medium/large traffic returns 503 until a link recovers.
- Brain A continues serving small-model traffic locally.

---

## Why not three brains? Four?

You could. Adding more brains makes sense when:
- A specific workload class (e.g., vision) warrants a dedicated node.
- Training loads are continuous and need their own permanent lane.

For now, two brains is the right shape because:
1. The **3090 is not a brain** — it's a compute endpoint. Device-class routing handles it.
2. The workers (M4 Max 36, M3 24) are **exo workers**, not brains. They get shards, not requests.
3. More brains = more routing complexity. Two is legible; four is a flowchart.

Revisit when:
- A fourth Apple Silicon Ultra joins (dedicated training brain).
- Vision workloads become a primary use case (vision brain with dedicated VLM).

---

## Operational notes

- **Brain A should never page to swap.** If `vm_stat` shows pageouts on M3 Ultra, a routing rule is wrong.
- **Brain B can swap briefly during model-swap.** Expected when hot-swapping resident models.
- **Metrics to watch:** Brain A request latency p50/p99, Brain B handoff rate, Brain B memory headroom, cross-brain RTT.
- **Single upgrade path:** When a newer Mac Studio ships (M5 Ultra, etc.), it can slot in as Brain A with zero topology changes — the M3 Ultra becomes a ring worker.

---

## Related documents

- [`CUDA-SIDECAR.md`](./CUDA-SIDECAR.md) — how the 3090 fits without being a brain
- [`ARCHITECTURE.md`](./ARCHITECTURE.md) — full cluster topology and rollout plan
- [`HARDWARE-REGISTRY.md`](./HARDWARE-REGISTRY.md) — per-node specs
- [`../configs/routing.yaml`](../configs/routing.yaml) — live routing policy
- [`../configs/supercomputer.yaml`](../configs/supercomputer.yaml) — cluster topology
