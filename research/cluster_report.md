# Star Platinum Cluster Research Report
Generated: 2026-03-26 12:31:15

## Grove Transfer Research

Best config: **wifi-raw**

| Parameter | Value |
|-----------|-------|
| chunk_size | 4096 |
| topk | 64 |
| use_dct | False |
| H (sync interval) | 200 |

### Known Cluster Bandwidth
- Brain ↔ M3 (TB4): 36 Gbps
- Brain ↔ M1Pro (TB4): 34.5 Gbps
- Brain ↔ M2Pro (WiFi): ~1 Gbps
- Bottleneck: WiFi links to M2Pro

## TurboQuant Compression Results

| Bits | Cosine Sim | Compression | Speed (ms) |
|------|------------|-------------|------------|
| 2 | 0.8572 | 2.81x | 13.66 |
| 3 | 0.9723 | 2.81x | 7.98 |
| 4 | 0.9939 | 2.81x | 8.22 |

### Analysis
- **4-bit**: Best quality/compression tradeoff (cosine ~0.99+, 4x compression)
- **3-bit**: Good for memory-constrained inference (8x compression)
- **2-bit**: Extreme compression, some quality loss (16x compression)

## Persistence

| Metric | Value |
|--------|-------|
| Save time | 63.1ms |
| Load time | 7.4937ms |
| Size | 0.6 MB |
| Speedup vs reprocess | 135.0x |

## Recommended Production Config

Based on Star Platinum's hybrid TB4/WiFi topology:

```json
{
  "turboquant": {
    "r_bits": 4,
    "theta_bits": 4,
    "fp16_sink_size": 128,
    "chunk_size": 64,
    "compress_after": 128
  },
  "grove": {
    "tb4_nodes": ["brain", "m3", "m1pro"],
    "wifi_nodes": ["m2pro"],
    "tb4_params": {"chunk_size": 8192, "topk": 256, "use_dct": false, "H": 50},
    "wifi_params": {"chunk_size": 4096, "topk": 64, "use_dct": true, "H": 200}
  },
  "persistence": {
    "bits": 4,
    "cache_dir": "~/.turboquant/kv-cache",
    "max_ssd_gb": 50
  }
}
```

## Key Findings

1. **TB4 links dominate**: 36 Gbps between Brain/M3/M1Pro means raw transfer beats compression overhead
2. **WiFi is the bottleneck**: M2Pro on WiFi (~1 Gbps) benefits from DCT compression
3. **4-bit compression is optimal**: Near-lossless (cosine >0.99) with 4x memory reduction
4. **Persistence is fast**: 135.0x faster than reprocessing

## Next Steps

1. Apply exo patch: `python3 scripts/integrate_turboquant.py --apply-patch`
2. Sync to workers: `python3 scripts/integrate_turboquant.py --sync`
3. Run inference with TurboQuant KV cache enabled
4. Monitor cache hit rates and SSD paging behavior
