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

## Node 4: Beast Linux (RDMA Server) — PENDING SPECS

## Node 5: MacBook Pro M2 Pro (Remote Access)

| Spec | Value |
|------|-------|
| **Model** | MacBook Pro (16-inch, M2 Pro, 2023) |
| **Model ID** | Mac14,10 (A2780) |
| **Model Number** | MNW93LL/A |
| **Chip** | Apple M2 Pro |
| **CPU** | 12-core (8 Performance + 4 Efficiency) |
| **GPU** | 19-core Apple GPU, Metal 4 |
| **GPU Compute** | ~7 TFLOPS FP32 / ~14 TFLOPS FP16 (estimated) |
| **Neural Engine** | 16-core ANE, 15.8 TOPS INT8 / **7.9 TFLOPS FP16 true** |
| **Memory** | 16 GB unified LPDDR5 |
| **Memory Bandwidth** | 200 GB/s |
| **Storage** | 500 GB SSD |
| **Thunderbolt** | **3× Thunderbolt 4** (USB-C), 40 Gbps |
| **HDMI** | 1× HDMI 2.1 |
| **Wi-Fi** | Wi-Fi 6E (802.11ax) |
| **Bluetooth** | 5.3 |
| **Display** | 16.2" 3456×2234 Liquid Retina XDR |

### Cluster role implications

- **16 GB memory**: Smallest memory in the cluster. Can hold ~8B param models max. Not viable for large model shards.
- **500 GB storage**: Smallest SSD. Limited model cache capacity.
- **3× Thunderbolt 4**: Same as iMac Pro speed (40 Gbps) but has 3 ports vs iMac Pro's 4. COULD be TB-connected to the cluster if needed.
- **7.9 TFLOPS ANE**: Lowest ANE in the cluster but still functional for light workloads.
- **200 GB/s bandwidth**: 2× the M3 base, decent for its memory size.
- **16-inch display**: Good for on-the-go monitoring/dashboard viewing.

### Cluster role: Remote access + light overflow

Originally described as "M2 iMac" — actually a MacBook Pro 16-inch. Role:
- SSH gateway into all cluster nodes + OpenClaw
- Portable monitoring (16" screen with dashboard)
- NOT connected via TB4 for data plane (per original plan)
- Could optionally join as a light ANE/GPU node if TB-connected

## Node 6: MacBook Air (SSH only) — PENDING SPECS

---

*Updated: March 2026*
*Run `system_profiler SPHardwareDataType SPDisplaysDataType SPThunderboltDataType` on each node to fill in specs.*
