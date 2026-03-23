# TB4 Throughput Benchmark Results 🖤

**Date:** 2026-03-23
**Link:** Brain (M4 Max en2) ↔ M3 (Mac15,3 bridge0)
**Transport:** TCP over IPv6 link-local (fe80::)
**Protocol:** Raw TCP socket, 4MB chunks, SO_SNDBUF=4MB, TCP_NODELAY

## Results

| Test | Size | Time | Throughput |
|------|------|------|------------|
| Quick test | 200MB | 0.07s | 23.47 Gbps |
| Sustained test | 2GB | 0.48s | **35.57 Gbps** |

**TB4 theoretical max:** 40 Gbps  
**Achieved efficiency:** 88.9% of line rate  
**vs WiFi baseline:** ~35x faster  
**Latency (ping6):** 0.56ms avg  

## Key Finding

No RDMA kernel hacks required. Plain TCP over TB4 IPv6 link-local achieves
near-line-rate throughput. The AppleThunderboltRDMA.kext is TB5-only but
TCP/IPv6 over the TB4 IP interface delivers comparable performance for
tensor transport use cases.

## TB4 Ring Status

| Link | Status | Speed |
|------|--------|-------|
| Brain → M3 | ✅ LIVE | 35.57 Gbps |
| M3 → M2 | 🔧 needs mapping | TBD |
| M2 → M1 | 🔧 needs mapping | TBD |
| M1 → Brain (ring close) | 🔧 needs mapping | TBD |

## IPv6 Link-Local Addresses (stable across reboots once set)

| Node | Interface | IPv6 LL | TB IP |
|------|-----------|---------|-------|
| Brain (M4 Max) | en2 | fe80::1c81:58ca:463a:ae03 | 10.42.0.1 |
| M3 (Mac15,3) | bridge0 | fe80::c6c:6e2d:d1f9:84ad | APIPA |
| M2 Pro | bridge0 | TBD | TBD |
| M1 Pro | bridge0 | TBD | TBD |

## Next Steps

1. Map M3→M2 and M2→M1 links (get their IPv6 LLs)
2. Wire TB4 transport into exo (replace WiFi TCP with TB4 TCP)
3. Enable IP forwarding chain for multi-hop routing
4. Run tensor parallel inference test across all 4 nodes
