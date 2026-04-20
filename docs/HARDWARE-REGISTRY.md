# HARDWARE REGISTRY

Single source of truth for Star Platinum cluster hardware. Update this file when nodes are added, reconfigured, or retired.

**Last updated:** 2026-04-16

---

## Active fleet

### Node 1 — `m3-ultra` (Brain A)

| Attribute | Value |
|---|---|
| Chassis | Mac Studio (2025) |
| Chip | Apple M3 Ultra |
| CPU | 28-core (20 performance + 8 efficiency), 4.0 GHz |
| GPU | 60-core Metal, hardware ray tracing |
| Neural Engine | 32-core (~38 TFLOPS FP16 est.) |
| Memory | 96 GB unified, 819 GB/s bandwidth |
| Storage | 1 TB SSD (not user-accessible) |
| Ports | 6× Thunderbolt 5, 2× USB-A, HDMI 2.1, 10GbE, SDXC |
| Headless | Yes (BetterDisplay 5K virtual screen, Parsec remote) |
| Network | Tailscale: `mac-studio.beardie-ph.ts.net` |
| Role | **Brain A** — OpenClaw runtime, orchestration, scheduler, routing |
| exo role | Master / primary scheduler |

### Node 2 — `m4-max-128` (Brain B)

| Attribute | Value |
|---|---|
| Chassis | MacBook Pro 14" |
| Chip | Apple M4 Max |
| CPU | 16-core (12P + 4E) |
| GPU | 40-core Metal |
| Neural Engine | 16-core (~19 TFLOPS FP16) |
| Memory | 128 GB unified |
| Storage | 1 TB SSD |
| Ports | 3× Thunderbolt 5, HDMI, SDXC |
| Headless | Yes (lid closed, external display not attached) |
| Role | **Brain B** — heavy inference, training, long-context |
| exo role | Primary worker, invoked by Brain A for size > 8B |

### Node 3 — `m3-24`

| Attribute | Value |
|---|---|
| Chassis | MacBook Pro 14" |
| Chip | Apple M3 |
| CPU | 8-core (4P + 4E) |
| GPU | 10-core Metal |
| Neural Engine | 16-core (~9 TFLOPS FP16) |
| Memory | 24 GB unified |
| Storage | 2 TB SSD |
| Ports | 2× Thunderbolt 4 |
| Role | Pipeline parallel worker, model cache |
| exo role | ANE worker |

### Node 4 — `m1-max-64` (active)

| Attribute | Value |
|---|---|
| Chassis | Mac Studio (2025) |
| Chip | Apple M4 Max |
| CPU | 14-core (10P + 4E) |
| GPU | 32-core Metal |
| Neural Engine | 16-core (~19 TFLOPS FP16) |
| Memory | 64 GB unified |
| Storage | 512 GB SSD |
| Ports | 4× Thunderbolt 5, HDMI, 10GbE |
| Role | Tensor parallel shard, ANE worker |
| exo role | ANE worker |
| Status | **Hardware active** |

### Node 5 — `rtx-3090` (CUDA sidecar, active)

| Attribute | Value |
|---|---|
| Enclosure | Sonnet Breakaway Box 850 T5 |
| GPU | NVIDIA RTX 3090 (Ampere) |
| VRAM | 24 GB GDDR6X |
| CUDA cores | 10,496 |
| TFLOPS | ~35 FP16, ~71 Tensor (FP16) |
| Connection | Thunderbolt 5 (80 Gbps) → attached to `m3-ultra` |
| Power | 850W internal PSU (GPU TDP 350W) |
| Driver | Tiny Corp eGPU driver (Apple-approved, compiled via Docker) |
| Role | CUDA-native inference (vLLM, exllama), QLoRA fine-tuning |
| exo role | Device-class `cuda` — routed via `configs/routing.yaml` |
| Status | **Hardware active** |
| Notes | Not on TB RDMA ring. No macOS display output — compute-only. |

### Node 6 — `beast`

| Attribute | Value |
|---|---|
| Chassis | Mac Pro 2013 (cylinder) |
| CPU | Intel Xeon E5-1680 v2 (8-core, 3.0 GHz) |
| GPU | Dual AMD FirePro D500 (3 GB each) — unused |
| Memory | 64 GB DDR3 ECC |
| Storage | 1 TB SSD (PCIe) + external |
| Network | 10GbE, Tailscale |
| TB ports | 4× Thunderbolt 3 (not on ring) |
| OS | **Linux** (file/Docker server) |
| Role | **File server** — cluster storage, Docker host, backups, `rdma-core` reference |
| Cluster link | Ethernet / Tailscale (not on TB RDMA ring) |

### Node 7 — `m2-air`

| Attribute | Value |
|---|---|
| Chassis | MacBook Air 2022 |
| Chip | Apple M2 |
| CPU | 10-core |
| GPU | 10-core Metal |
| Neural Engine | 16-core |
| Memory | 16 GB unified |
| Ports | 2× USB4 |
| Role | Remote SSH access + OpenClaw client for mobile use |
| Cluster link | Tailscale (not on TB ring) |

---

## Retired nodes

| Node | Chip | Memory | Retirement reason |
|---|---|---|---|
| `m1-pro` | M1 Pro | 16 GB | Sold to fund more CUDA (3090 / 5090) |
| `m2-pro` | M2 Pro | 16 GB | Sold to fund more CUDA |
| `imac-pro` | Xeon W-2140B + Vega 64 | 32 GB | Retired entirely (reassigned to other work) |

---

## Totals

| Metric | Apple Silicon ring | CUDA sidecar | Combined |
|---|---|---|---|
| Nodes | 4 | 1 | 5 compute |
| Unified memory | 284 GB | — | — |
| CUDA VRAM | — | 24 GB | 24 GB |
| ANE TFLOPS (FP16) | ~80 | — | ~80 |
| Apple GPU TFLOPS (FP16) | ~90 | — | ~90 |
| CUDA TFLOPS (FP16 tensor) | — | ~71 | ~71 |

**Plus:** 64 GB on Beast (CPU compute, storage), 24 GB on M2 Air (remote control).

---

## Thunderbolt topology

```
                     M3 Ultra (Brain A)
                          │
         ┌────────────────┼──────────────────┐
      TB5│120G        TB5│80G            TB5│120G
         ▼                ▼                   ▼
   M4 Max 128        RTX 3090             M4 Max 36
   (Brain B)       (CUDA sidecar          (worker)
                    — off-ring)                │
         │                                     │
         └────────────TB4 ring (40G)───────────┤
                          │                    │
                          ▼                    │
                      M3 24GB ─────────────────┘
                      (worker)
```

Ring links: **M3 Ultra ↔ M4 Max 128 ↔ M4 Max 36 ↔ M3 24 ↔ M3 Ultra** (4-node Apple Silicon DMA ring).
Sidecar: **M3 Ultra ↔ 3090** via TB5, CUDA-only, off-ring.

---

## Change log

- **2026-04-16** — Major fleet rewrite. M3 Ultra promoted to Brain A. M4 Max 128 → Brain B. M4 Max 36 added (active). RTX 3090 added as CUDA sidecar (active). M1 Pro, M2 Pro, iMac Pro retired. Beast confirmed Linux on TB3 (4 ports, not on ring).
- **2026-03-26** — Grove autoresearch run: `wifi-raw` config wins for mixed-topology.
- **2026-01-XX** — TurboQuant-MLX PR #1 merged into TriAttention.
- **2025-12-XX** — exo scheduler replaced legacy custom scheduler.
- **2025-11-XX** — 4-node RDMA ring bringup (original M4 Max MBP / M1 Pro / M2 Pro / M3 / iMac Pro).
