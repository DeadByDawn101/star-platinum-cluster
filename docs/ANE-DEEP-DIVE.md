# ANE Deep Dive — Hardware Architecture for Star Platinum Cluster

## Source
name99-org/AArch64-Explore, vol7 ANE.nb.pdf (v0.93)
Comprehensive reverse-engineering of Apple Neural Engine from patent analysis + benchmarks.

---

## Key Hardware Facts

### Core Architecture (per ANE core)

- **256 Multiply-Add (MAD) units per core** — the fundamental compute unit
- **FP16 and INT8 deliver the SAME throughput** — 256 MADs either way
  - This is why Apple's "38 TOPS INT8" = 19 TFLOPS FP16 — not 2x, just same hardware
  - The MADs handle FP16×FP16, INT8×INT8, and even mixed INT8×FP16
- **Accumulation in FP32/INT32** — products accumulated at higher precision (like NVIDIA TF32)
- **Input Buffer: 512 bytes** — holds the work unit data fed to MADs
- **8 accumulator registers per MAD** — enables multi-cycle operations (e.g., 9 cycles for 3×3 convolution)
- **Post-Processor** per core — handles ReLU, normalization, data format conversion after compute

### System Architecture

- **16 cores** on A14/M1 and all subsequent M-series (was 8 on A12/A13)
- **4 chains of 4 cores** — cores grouped into chains for producer/consumer pipelining
- **4 MB "Smart L2" Data Buffer** (on M1) — manually managed SRAM, not a cache
  - Compiler explicitly controls what goes in/out
  - Routes data between producers and consumers with flow control
  - NOT for long-term data reuse — it's a communication buffer
- **Push architecture via DMA** — no load/store instructions
  - Two DMA engines: one for signal data, one for kernel/weight data
  - Program interleaves DMA commands with compute commands
  - DMA can reformat/rearrange data during transfer
- **Kernel compression** — weights stored compressed, decompressed by Kernel Extract unit on-the-fly

### Clock and Performance

| Chip | Cores | MADs/Core | Clock (est.) | INT8 TOPS | FP16 TFLOPS |
|------|-------|-----------|-------------|-----------|-------------|
| A12/A13 | 8 | 256 | ~1.0 GHz | ~4 | ~4 |
| A14/M1 | 16 | 256 | ~1.2 GHz | ~11 | ~11 |
| A15/M2 | 16 | 256 | ~1.2 GHz | ~15.8 | ~15.8 |
| A16/M3 | 16 | 256 | ~1.4 GHz | ~18 | ~18 |
| A17/M4 | 16 | 256 | ~1.5 GHz | ~38* | ~19** |

*Apple's marketing TOPS for M4. **True FP16 TFLOPS from maderix research.

The discrepancy in M4 numbers: Apple may be counting additional operations from the
Post-Processor or Data Buffer rearrangement, or they may have doubled the INT8 path
width while keeping FP16 the same.

### Our Cluster ANE Budget

| Node | Chip | ANE TFLOPS FP16 | MADs Total |
|------|------|-----------------|------------|
| M4 Max | M4 Max | 19.0 | 4,096 |
| M1 Pro | M1 Pro | 11.0 | 4,096 |
| M3 | M3 | 9.0 | 4,096 |
| M2 Pro | M2 Pro | 7.9 | 4,096 |
| **Total** | | **46.9** | **16,384** |

Every node has the same 16 cores × 256 MADs = 4,096 MADs. The TFLOPS difference
is purely clock speed. This means workloads can be evenly distributed across cores
with only timing adjustments needed.

---

## How ANE Processes Neural Networks

### The Pipeline

```
                    DMA Engine
                    ├── Signal DMA → Data Buffer (Smart L2, 4MB)
                    └── Kernel DMA → Kernel Storage (compressed)
                            │
                            ▼
              ┌─────────────────────────────┐
              │     Neural Core (×16)        │
              │                              │
              │  Input Buffer (512B)         │
              │       │                      │
              │  Shifter/Rasterizer          │
              │       │ (address generation) │
              │  256× Multiply-Add Units     │
              │       │                      │
              │  Accumulator (8 regs/MAD)    │
              │       │                      │
              │  Post-Processor              │
              │  (ReLU, norm, format conv)   │
              │       │                      │
              │  Output (resequence/reformat)│
              └─────────────────────────────┘
                            │
                    Chain Buffer → Data Buffer → DMA out
```

### Key Insight: Push Architecture

The ANE is fundamentally different from CPU/GPU:
- **No load/store** — cores don't request data
- **DMA pushes data in** — the compiler schedules exactly when data arrives
- **Compute happens when data arrives** — no stalls, no cache misses
- **Output is DMA'd back out** — results written to system memory by DMA

This means latency is PREDICTABLE. Once a layer starts, it runs autonomously
through the Rasterizer/Shifter hardware loops without any software intervention.

### What ANE Does Well

- **Convolutions** (3×3, 5×5) — the original design target
- **Matrix-vector multiply** — weights × signal, the core of LLM inference
- **Depthwise separable convolutions** — efficient on the per-core architecture
- **ReLU and common activation functions** — in Post-Processor hardware
- **Data reformatting** — DMA handles layout changes during transfer

### What ANE Does NOT Do Well

- **FP32** — cannot run on ANE at all, falls to GPU or AMX
- **Custom activation functions** (log, exp, sin) — not in Post-Processor lookup
- **Dynamic branching** within layers (added in 2021 patents, limited)
- **Extremely large matrices** — limited by Data Buffer size, needs tiling
- **Training backprop** — designed for inference, training support is limited

---

## Implications for LLMs on Star Platinum

### The LLM Challenge for ANE

From the paper's analysis:

1. **ANE was designed for vision, not language** — the 1.0 architecture is optimized
   for 2D convolutions on images. LLMs need matrix-vector multiplies on 1D token
   sequences.

2. **Matrix-vector multiply IS supported** — it maps to the same MAD hardware, just
   with different Rasterizer/Shifter patterns. The compiler handles this.

3. **Attention mechanism is the bottleneck** — self-attention requires matrix-matrix
   multiply (QKV), which the ANE handles as tiled matrix-vector operations.

4. **SLC (System Level Cache) matters enormously** — benchmarks show Pro/Max chips
   (with larger SLC) run ANE workloads significantly faster than base chips. The SLC
   buffers data between system memory and the ANE's Data Buffer.
   - M4 Max has the largest SLC → best ANE throughput
   - M3 base has smallest SLC → may bottleneck on large models

5. **Sparsity is the future** — Apple's own research (ReLU Strikes Back, 2023)
   shows 90% sparsity in activations with ReLU. Future ANE hardware likely
   optimized for sparse matrix operations.

### How exo Should Use ANE

Based on the hardware architecture, the optimal strategy for our cluster:

**Prefill phase** (processing the full prompt):
- This is matrix-MATRIX multiply (batch of tokens × weight matrix)
- ANE excels here — all 256 MADs per core fully utilized
- Distribute across all 4 ANE nodes proportional to TFLOPS
- M4 Max handles 40% of layers, M1 Pro 24%, M3 19%, M2 Pro 17%

**Decode phase** (generating one token at a time):
- This is matrix-VECTOR multiply (single token × weight matrix)
- ANE is less efficient — only a fraction of MADs utilized per cycle
- GPU may be faster for decode on nodes with powerful GPUs (M4 Max: 40-core)
- **Hybrid strategy:** ANE prefill + GPU decode

**Key optimization: Keep weights in Data Buffer**
- The 4MB Smart L2 per ANE can hold a significant chunk of model weights
- If the compiler tiles layers correctly, weights stay resident between tokens
- This avoids the DMA round-trip to system memory on every token

### QoS for Distributed Inference

From maderix research (already in our ANE compute backend):
- **Real-time QoS (0x31)** for inference — highest priority
- **Background QoS (0x09)** for gradient reduction — never interrupts inference
- **127-deep evaluation queue** — pipeline multiple layers simultaneously
- At 32+ chained operations: 94% utilization → ~17.9 sustained TFLOPS on M4 Max

---

## Architecture Generations (for reference)

| Version | Chips | Year | Key Changes |
|---------|-------|------|-------------|
| 1.0 | A11 | 2017 | First ANE, 2 cores, vision-only |
| 2.0 | A12, A13 | 2018-19 | 8 cores, mixed precision (FP16+INT8), programmable |
| 3.0 | A14, M1 | 2020 | 16 cores, 4-core chains, Smart L2 enhancements |
| 3.x | A15, M2 | 2021-22 | Task scheduling improvements, conditional branching |
| 4.0 | A16, M3 | 2022-23 | Higher clocks, compiler improvements |
| 4.x | A17, M4 | 2023-24 | Possible doubled INT8 path, further compiler optimization |

---

## References

- name99-org, "AArch64-Explore vol7 ANE.nb" (v0.93)
- Apple Patents: US20190340491A1 (Scalable Neural Processing Engine)
- Apple Patents: US20220036163A1 (Chained Neural Engine Write-back)
- Apple Patents: US20220237439A1 (Branching Operation)
- Apple Patents: US20220237438A1 (Task Context Switching)
- maderix ANE research (in our ANE repo)
- hollance/neural-engine (community reference)
- tinygrad ANE accelerator code
