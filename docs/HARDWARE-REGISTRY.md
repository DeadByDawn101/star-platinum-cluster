# RavenX Cluster — Hardware Registry

## Node 1: iMac Pro (Control Center)

| Spec | Value |
|------|-------|
| **Model** | iMac Pro (Late 2017) |
| **Model ID** | iMacPro1,1 (A1862) |
| **CPU** | Intel Xeon W-2140B, 8-core / 16-thread, 3.2 GHz (Turbo 4.2 GHz) |
| **L2 Cache** | 1 MB per core (8 MB total) |
| **L3 Cache** | 11 MB |
| **RAM** | 32 GB DDR4 ECC 2666 MHz |
| **Storage** | 1 TB SSD (3.3 GB/s read, 2.8 GB/s write) |
| **GPU** | AMD Radeon Pro Vega 56, 8 GB HBM2 |
| **GPU Compute** | ~11 TFLOPS FP32 / ~22 TFLOPS FP16 |
| **ANE** | **NONE** (Intel, pre-Apple Silicon) |
| **Thunderbolt** | **4× Thunderbolt 3** (USB-C), 40 Gbps, dual-bus |
| **Ethernet** | 10 Gb Nbase-T |
| **USB** | 4× USB 3.0 Type-A |
| **Bluetooth** | 4.2 |
| **Wi-Fi** | 802.11ac |
| **Security** | Apple T2 chip (Secure Enclave, encrypted storage) |

### Cluster role implications

- **No ANE**: Cannot run ANE compute workloads. Role is purely control plane + Vega GPU compute.
- **Thunderbolt 3** (not TB4/TB5): Still 40 Gbps, same raw bandwidth as TB4. But lacks TB4's mandatory Intel VT-d DMA protection and USB4 tunneling. OdinLink *may* work over TB3 since the NHI ring DMA mechanism is fundamentally the same, but untested.
- **Vega 56 GPU**: 22 TFLOPS FP16 via Metal 3. This is actually MORE raw FP16 TFLOPS than a single M4 Max ANE (19 TFLOPS). Could serve as a GPU compute node for specific workloads.
- **10GbE**: Can serve as a high-speed network fallback if TB3 proves problematic for RDMA.
- **ECC RAM**: 32 GB ECC — reliability advantage for long-running cluster operations.
- **Intel x86**: Can run standard Linux tools, rdma-core, etc. if needed. macOS on Intel supports a different set of frameworks than Apple Silicon.

### Revised cluster role

The iMac Pro should be recategorized from "TB4 control center" to:
- **Cluster control plane** (exo dashboard, monitoring, scheduling)
- **GPU compute node** (Vega 56 for Metal workloads, 22 TFLOPS FP16)
- **Network bridge** (TB3 hub connecting M4 Max ↔ Beast via dual TB3 buses)
- **NOT an ANE node** (zero ANE capability)

---

## Node 2: MacBook Pro M4 Max (Brain)

| Spec | Value |
|------|-------|
| **Model** | MacBook Pro (14-inch, M4 Max, 2024) |
| **Model ID** | Mac16,6 (A3185) |
| **Chip** | Apple M4 Max |
| **CPU** | 16-core (12 Performance + 4 Efficiency) |
| **GPU** | 40-core Apple GPU, Metal 4 |
| **GPU Compute** | ~54 TFLOPS FP16 (estimated from 40-core M4 Max benchmarks) |
| **Neural Engine** | 16-core ANE, 38 TOPS INT8 / **19 TFLOPS FP16 true** |
| **Memory** | **128 GB** unified LPDDR5X |
| **Memory Bandwidth** | 546 GB/s |
| **Storage** | 1 TB SSD |
| **Thunderbolt** | **3× Thunderbolt 5** (USB-C), 120 Gbps max |
| **HDMI** | 1× HDMI 2.1 |
| **Wi-Fi** | Wi-Fi 6E (802.11ax) |
| **Bluetooth** | 5.3 |
| **Display** | 14.2" 3024×1964 Liquid Retina XDR |

### Cluster role: Brain

- **128 GB unified memory**: Fits Qwen 72B+ entirely in memory. Crown jewel of the cluster.
- **Thunderbolt 5**: 120 Gbps (3× the iMac Pro's TB3). Native OdinLink target. 3 ports = direct links to 2 nodes + 1 peripheral.
- **19 TFLOPS ANE**: Primary ANE compute. At 94% utilization (32+ chained ops) = ~17.9 sustained TFLOPS.
- **~54 TFLOPS GPU**: 40-core Metal 4 GPU. Handles decode phase in hybrid ANE-prefill/GPU-decode strategy.
- **546 GB/s bandwidth**: Feeds ANE + GPU without bottleneck for large model inference.

## Node 3: MacBook Pro M3 (ANE Worker)

| Spec | Value |
|------|-------|
| **Model** | MacBook Pro (14-inch, M3, Late 2023) |
| **Model ID** | Mac15,3 (A2918) |
| **Chip** | Apple M3 (base) |
| **CPU** | 8-core (4 Performance + 4 Efficiency), 4.05 GHz |
| **GPU** | 10-core Apple GPU, Metal 4 |
| **GPU Compute** | ~3.6 TFLOPS FP32 / ~7 TFLOPS FP16 (estimated) |
| **Neural Engine** | 16-core ANE, 18 TOPS INT8 / **9 TFLOPS FP16 true** |
| **Memory** | 24 GB unified LPDDR5 |
| **Memory Bandwidth** | 100 GB/s |
| **Storage** | 2 TB SSD |
| **Thunderbolt** | **2× Thunderbolt 4** (USB-C), 40 Gbps |
| **HDMI** | 1× HDMI 2.1 |
| **Wi-Fi** | Wi-Fi 6E (802.11ax) |
| **Bluetooth** | 5.3 |
| **Display** | 14.2" 3024×1964 Liquid Retina XDR |

### Cluster role implications

- **Base M3, NOT M3 Pro/Max**: This is the entry-level chip. Only 8 CPU cores, 10 GPU cores, 24 GB RAM. Significantly less capable than the M4 Max brain.
- **Only 2× Thunderbolt 4** (not TB5): 40 Gbps, same as iMac Pro TB3. The M4 Max has 3× TB5 at 120 Gbps — the link from M4 Max to this node will be bottlenecked at 40 Gbps by this end.
- **9 TFLOPS FP16 ANE**: Half the M4 Max's ANE throughput. Still useful but not a powerhouse. The M3 ANE is the same 16-core design but clocked lower.
- **24 GB memory**: Can hold ~12B parameter models. Too small for 32B+ without sharding.
- **100 GB/s bandwidth**: 5.5× slower than M4 Max. Will bottleneck large model inference.
- **2 TB storage**: Largest SSD in the cluster. Good candidate for model cache and checkpoint staging.

### Revised cluster role

Original plan called this "ANE worker" with assumed M4-class specs. Reality check:
- **Light ANE compute node**: 9 TFLOPS ANE, useful for pipeline parallel shards of smaller layers
- **Overflow storage**: 2 TB SSD for model/checkpoint staging
- **Pipeline parallel tail**: In a 2-node pipeline (M4 Max + M3), the M3 handles the last N layers proportional to its 24 GB (exo's memory-proportional sharding)
- **NOT a primary compute peer**: The M4 Max has 5.3× more memory, 5.5× more bandwidth, 2× more ANE TFLOPS, and 3× faster TB links

## Node 4: Mac Pro 2013 "Trashcan" — Beast Linux

| Spec | Value |
|------|-------|
| **Model** | Mac Pro (Late 2013) "Trashcan" |
| **Model ID** | MacPro6,1 |
| **OS** | Ubuntu Linux (kernel 6.8.0-101-generic) |
| **CPU** | Intel Xeon E5-1680 v2, 8-core / 16-thread, 3.0 GHz (Turbo 3.9 GHz) |
| **RAM** | **64 GB** DDR3 ECC 1866 MHz |
| **GPU** | 2× AMD Radeon HD 7870 XT (Tahiti LE / FirePro D700) |
| **GPU Compute** | ~5 TFLOPS FP32 combined (GCN 1.0, no modern compute) |
| **ANE** | **NONE** (Intel x86) |
| **Storage** | 1 TB Apple SSD SM1024 |
| **Thunderbolt** | **Thunderbolt 2** (Falcon Ridge DSL5520), 3× NHI controllers, **20 Gbps** |
| **Ethernet** | 2× Gigabit (enp11s0 active, enp12s0 down) |
| **USB** | USB 2.0 (EHCI) + USB 3.0 (Fresco Logic FL1100) |
| **Networking** | Tailscale VPN active, Docker with multiple bridge networks |
| **RDMA** | **NOT installed** — no hardware RDMA (no IB HCA, no RoCE NIC) |

### Critical findings — THIS CHANGES THE ARCHITECTURE

1. **Thunderbolt 2 (20 Gbps), NOT TB3/TB4/TB5**: The Falcon Ridge DSL5520 is a 2013 TB2 controller. OdinLink requires TB4/TB5 NHI ring DMA — a completely different hardware interface. **OdinLink will NOT work on this machine.** The NHI register set and ring descriptor format are incompatible.

2. **Kernel 6.8.0**: OdinLink requires kernel 6.18+. Even if TB2 were compatible, the kernel is too old. Upgrading is possible but doesn't fix the TB2 hardware limitation.

3. **No RDMA hardware**: No InfiniBand HCA, no RoCE NIC. rdma-core can be installed but there's nothing to drive. Software RDMA (rxe/SoftiWARP) is possible but runs over Ethernet at CPU cost — no hardware offload.

4. **Dual GPUs are obsolete**: Radeon HD 7870 XT is 2012 GCN 1.0. No ROCm, no Metal, no modern compute API. Display-only.

5. **64 GB RAM is the saving grace**: Second-largest memory pool after the M4 Max. Useful for CPU workloads.

6. **Already a Docker server**: Running containers with bridge networks. Functional infrastructure host.

7. **Tailscale active**: Reachable remotely. Good for management plane.

8. **1 Gbps Ethernet only**: This is the realistic data link speed to the cluster. 100× slower than even TB3.

### Revised cluster role

The Beast **cannot** be an RDMA transport node. New role:
- **Docker service host**: DirectReduce as a containerized service, monitoring stacks, API gateways
- **CPU compute**: 8-core Xeon + 64 GB for tokenization, data preprocessing, checkpoint management
- **Network storage**: 1 TB SSD over Gigabit Ethernet (or Tailscale)
- **Software-only DirectReduce**: Python/numpy gradient reduction, but at 1 Gbps speeds
- **NOT on the Thunderbolt data plane**: TB2 is incompatible with entire cluster RDMA strategy

---

## Node 5: MacBook Pro M2 Pro 16" (Role TBD)

| Spec | Value |
|------|-------|
| **Model** | MacBook Pro (16-inch, M2 Pro, 2023) |
| **Model ID** | Mac14,10 (A2780) |
| **Chip** | Apple M2 Pro |
| **CPU** | 12-core (8P + 4E) |
| **GPU** | 19-core Apple GPU, Metal 4 |
| **Neural Engine** | 16-core ANE, 15.8 TOPS INT8 / **7.9 TFLOPS FP16 true** |
| **Memory** | 16 GB unified LPDDR5 @ 200 GB/s |
| **Storage** | 500 GB SSD |
| **Thunderbolt** | **3× Thunderbolt 4** (USB-C), 40 Gbps |

### Cluster role: AWAITING ASSIGNMENT

This machine has 3× TB4 ports and ANE compute. Could potentially:
- Replace the Beast as a TB4-connected compute node
- Serve as a third ANE node in the ring (7.9 TFLOPS)
- Act as portable cluster monitoring/access

---

## Node 6: MacBook Air M2 (Remote SSH Access)

| Spec | Value |
|------|-------|
| **Model** | MacBook Air (M2, 2022) |
| **Chip** | Apple M2 |
| **ANE** | 16-core, 15.8 TOPS INT8 / ~7.9 TFLOPS FP16 |
| **Thunderbolt** | 2× Thunderbolt / USB 4 (MagSafe charging) |

*Role: SSH remote access into all cluster nodes + OpenClaw. Not on TB data plane.*

---

*Updated: March 2026*
*Run `system_profiler SPHardwareDataType SPDisplaysDataType SPThunderboltDataType` on each node to fill in specs.*

---

## Node 7: MacBook Pro M1 Pro 16" (ANE Compute)

| Spec | Value |
|------|-------|
| **Model** | MacBook Pro (16-inch, M1 Pro, 2021) |
| **Model ID** | MacBookPro18,1 (A2485) |
| **Chip** | Apple M1 Pro |
| **CPU** | 10-core (8P + 2E), 3.2 GHz |
| **GPU** | 16-core Apple GPU, Metal 3 |
| **GPU Compute** | ~5.2 TFLOPS FP16 |
| **Neural Engine** | 16-core ANE, 22 TOPS INT8 / **11.0 TFLOPS FP16 true** |
| **Memory** | 16 GB unified LPDDR5 @ 200 GB/s |
| **Memory Bandwidth** | 200 GB/s |
| **Storage** | 1 TB SSD |
| **Thunderbolt** | **3× Thunderbolt 4** (USB-C), 40 Gbps |
| **HDMI** | 1× HDMI 2.0 |
| **MagSafe** | MagSafe 3 charging |
| **Wi-Fi** | Wi-Fi 6 (802.11ax) |
| **Bluetooth** | 5.0 |

### Cluster role: ANE Compute Node

- **11 TFLOPS FP16 ANE**: Second-highest ANE throughput after M4 Max (19T). This is a serious compute node.
- **3× Thunderbolt 4**: Full ring connectivity — can link to 2 nodes + 1 peripheral.
- **16 GB unified memory**: Same as M2 Pro. Can hold ~8B parameter models. Shards of larger models via exo.
- **200 GB/s bandwidth**: 2× the M3, same as M2 Pro. Good ANE feed rate.
- **1 TB SSD**: Matches M4 Max storage. Ample model cache.
- **M1 Pro architecture**: First-gen Apple Silicon pro chip. Proven stable, well-understood by exo.

### Ring position: Between M4 Max and M3

The M1 Pro's 3× TB4 ports make it the ideal second hop from the M4 Max brain.
Its 11 TFLOPS ANE is the second-strongest compute in the ring, so placing it
adjacent to the brain minimizes latency for the heaviest shards.

