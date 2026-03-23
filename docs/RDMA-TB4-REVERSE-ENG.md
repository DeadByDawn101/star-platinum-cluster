# RDMA over TB4 — Reverse Engineering Plan 🖤

## The Core Problem

TB4 = PCIe tunneling + DisplayPort + USB3 over a single cable.
TB5 = same + native 120Gbps + Apple RDMA framework built in.

We have TB4 (40Gbps) on M1 Pro, M2 Pro, M3, iMac Pro.
We have TB5 (120Gbps) only on M4 Max.

**Goal:** Build zero-copy tensor transport over TB4 that approaches RDMA latency (<50μs per transfer vs ~200μs TCP today).

---

## What TB4 Actually Gives Us

```
TB4 Physical Layer
├── PCIe tunnel (16 GT/s, ~25Gbps effective data)
├── DisplayPort tunnel (8.1 Gbps)
└── USB3.2 tunnel (10 Gbps)

What we use: PCIe tunnel → Thunderbolt IP (thunderbolt-net)
Current path: TCP/IP over thunderbolt-net → ~1-2 Gbps real throughput
What we want: mmap DMA over PCIe tunnel → ~20-25 Gbps, <50μs
```

---

## The Ring Topology (Physical Cable Runs Needed)

```
M4 Max ──TB5→TB4 cable──▶ M1 Pro ──TB4→TB3 cable──▶ iMac Pro
  ▲                                                      │
  │ TB5→TB4 cable                              TB3→TB4 cable
  │                                                      ▼
 M3 (Mac15,3) ◀──TB4 cable── M2 Pro (Mac14,10) ◀────────┘
```

### Cable Runs Required (5 cables total):

| Run | From | To | Cable Needed | Length Est |
|-----|------|----|--------------|------------|
| 1 | M4 Max TB5 port | M1 Pro TB4 port | TB4 cable (40G) | ~1-2m |
| 2 | M1 Pro TB4 port | iMac Pro TB3 port | TB3 cable (40G) | ~1-2m |
| 3 | iMac Pro TB3 port | M2 Pro TB4 port | TB3 cable (40G) | ~1-2m |
| 4 | M2 Pro TB4 port | M3 TB4 port | TB4 cable (40G) | ~1-2m |
| 5 | M3 TB4 port | M4 Max TB5 port | TB4 cable (40G) | ~1-2m |

**Buy list:**
- 3× Thunderbolt 4 cable (40Gbps, passive, 1-2m) — ~$30-50 each
- 2× Thunderbolt 3 cable (40Gbps, 1-2m) — ~$20-30 each
- Total: ~$130-200

**Note:** TB5→TB4 cables work — TB5 is backward compatible. Any quality TB4 cable works.

---

## Software Architecture: Zero-Copy Transport over TB4

### Layer 1: Thunderbolt IP (already works, just slow)
macOS automatically creates a `bridge100` or `thunderbolt0` interface when TB cable is connected.
Current exo traffic uses TCP over this — good for control plane, bad for tensors.

### Layer 2: What We Want — mmap DMA Transport

```
Node A (sender)                    Node B (receiver)
┌─────────────────┐                ┌─────────────────┐
│  MLX tensor     │                │  MLX tensor     │
│  (metal buffer) │                │  (metal buffer) │
└────────┬────────┘                └────────▲────────┘
         │ IOSurface               IOSurface │
         │ mmap region             mmap region
         ▼                                  │
┌─────────────────┐    PCIe tunnel  ┌──────────────────┐
│  TB4 DMA engine │ ─────40Gbps───▶ │  TB4 DMA engine  │
│  (peer memory)  │                 │  (peer memory)   │
└─────────────────┘                 └──────────────────┘
```

### The Key Insight: Thunderbolt Peer Memory Access

TB4 supports **peer memory access** via PCIe BAR (Base Address Register) mapping.
When two Macs are connected via TB4, the PCIe tunnel allows one side to map the other's memory space.

macOS exposes this through `IOThunderboltFamily` and `IOPCIFamily`.

---

## Reverse Engineering Path

### Step 1: Enumerate TB4 PCIe devices
```bash
# On M4 Max with TB cable to M1 Pro connected
system_profiler SPThunderboltDataType
ioreg -l -p IOService -c IOThunderboltController | grep -i "peer\|BAR\|memory\|DMA"
```

### Step 2: Find the peer memory BAR
```bash
# Check PCIe BARs exposed by TB4 controller
ioreg -l -c IOPCIDevice | grep -A20 "Thunderbolt"
# Look for: "IOMemoryMap", "BAR0", "BAR1" entries with large address ranges
```

### Step 3: Map peer memory (prototype in Python)
```python
import ctypes
import mmap
import os

# TB4 peer memory appears as a PCIe device
# Map the BAR into our address space
def map_tb4_peer_memory(device_path: str, bar_offset: int, size: int):
    fd = os.open(device_path, os.O_RDWR)
    mapping = mmap.mmap(fd, size, offset=bar_offset)
    return mapping

# Once mapped, memcpy into/from this region = DMA transfer
# No TCP, no serialization, direct memory write
```

### Step 4: Wire into exo transport
```python
# src/exo/transport/rdma_tb4.py

class TB4Transport:
    """Zero-copy tensor transport over TB4 peer memory"""
    
    async def send_tensor(self, tensor: mx.array, peer_node: str) -> None:
        peer_bar = self._peer_bars[peer_node]
        # Get metal buffer backing the tensor
        metal_buf = tensor.__mlx_array_buf__()
        # DMA directly into peer BAR
        ctypes.memmove(peer_bar.address, metal_buf.contents, tensor.nbytes)
        # Signal completion via lightweight TCP control message
        await self._control_channel.signal_ready(peer_node, tensor.shape, tensor.dtype)
    
    async def recv_tensor(self, shape, dtype) -> mx.array:
        # Wait for signal
        meta = await self._control_channel.wait_ready()
        # Read from our BAR (already written by peer DMA)
        buf = self._local_bar.read(meta.nbytes)
        return mx.array(buf, dtype=dtype).reshape(shape)
```

---

## Realistic Performance Targets

| Transport | Latency | Throughput | Notes |
|-----------|---------|------------|-------|
| TCP/IP over TB4 (current) | ~200-500μs | ~1-2 Gbps | Software TCP stack overhead |
| Unix socket over TB4 | ~100-200μs | ~5 Gbps | Bypasses TCP, still copies |
| mmap shared memory (same host) | ~1-5μs | ~100 Gbps | Zero copy, same machine only |
| TB4 peer memory (target) | ~20-50μs | ~15-25 Gbps | PCIe tunnel, zero copy, cross-machine |
| TB5 native RDMA (M4 Max only) | ~5-10μs | ~40-80 Gbps | Apple RDMA framework |

**Realistic target for TB4 zero-copy:** 15-20 Gbps, 20-50μs latency
That's **10-15x improvement** over current TCP path.

---

## Implementation Phases

### Phase 3A — Software Zero-Copy (2-3 days, no cables needed yet)
Replace TCP tensor transport with Unix socket + `sendfile()` / `splice()` for same-host transfers.
Also implement `setsockopt(SO_ZEROCOPY)` for cross-host TCP.
**Target:** 3-5 Gbps, ~50μs (2-3x improvement, zero hardware cost)

### Phase 3B — TB4 IP Optimization (cables needed)
1. Connect the ring physically (buy 5 cables)
2. Use `setsockopt(TCP_NODELAY)` + `SO_ZEROCOPY` over TB4 IP interface directly
3. Tune MTU to 9000 (jumbo frames) on thunderbolt interfaces
**Target:** 8-12 Gbps, ~100μs

### Phase 3C — TB4 Peer Memory (advanced, 1-2 weeks)
1. Enumerate TB4 PCIe BARs via IOKit
2. Build mmap transport layer
3. Wire into exo's transport abstraction
**Target:** 15-25 Gbps, <50μs

### Phase 3D — TB5 RDMA on M4 Max (future)
Use Apple's private RDMA framework (same approach as our ANE work — observe & manifest).
**Target:** 40+ Gbps, <10μs

---

## First Thing To Do Right Now

Before buying cables — validate the TB4 IP path is even set up:

```bash
# On M4 Max, check if thunderbolt network interface exists
networksetup -listallhardwareports | grep -i thunder
ifconfig | grep -i thunder

# If not, connect a cable and check again
# macOS auto-creates the interface on cable connect
```

If we see `bridge100` or `en5` (thunderbolt) — the IP path is live and we can start Phase 3B immediately with just cables.

---

## What The Cluster Looks Like After RDMA

```
Current (WiFi/Ethernet):  ~1 Gbps between nodes, 200-500μs latency
After Phase 3B (TB4 IP):  ~8-12 Gbps, ~100μs — tensor sharding becomes practical
After Phase 3C (peer mem): ~20 Gbps, ~30μs — true distributed inference
Full ring total bandwidth:  ~100 Gbps aggregate across 5 links
```

At that point, splitting a 70B model across 4 nodes is not just possible — it's fast.
Llama 3.3 70B inference at 40Gbps = 1.5 seconds per full model weight pass.
With 128GB on brain alone we can already run 70B — RDMA makes the ring do 200B+.

---

*RavenX LLC — 2026. Zero compromises.* 🖤
