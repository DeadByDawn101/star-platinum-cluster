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

## Node 2: M4 Max (Brain) — PENDING SPECS

## Node 3: Mac Node 2 (ANE Worker) — PENDING SPECS

## Node 4: Beast Linux (RDMA Server) — PENDING SPECS

## Node 5: M2 iMac (Remote Access) — PENDING SPECS

## Node 6: MacBook Air (SSH only) — PENDING SPECS

---

*Updated: March 2026*
*Run `system_profiler SPHardwareDataType SPDisplaysDataType SPThunderboltDataType` on each node to fill in specs.*
