# EXO v1.0.70 Upgrade — Star Platinum

> Released: April 17, 2026. Installed across all 4 cluster nodes.

## Key Features for Star Platinum

### Models
- **Gemma 4 support** (#1851, #1891) — our primary model runs natively
- Minimax M2.7 and Qwen3.6 support added

### Performance (critical for us)
- **Flash Attention** for Qwen3.5 and Gemma 4 — 3-6x peak memory reduction
- KV prefix cache hit rate improvements
- Garbage collection on KV cache eviction
- Memory leak fixes in Rotating and Arrays cache

### RDMA Fixes (our Nack storm)
- **Clean RDMA resource cleanup** (#1889) — fixes zombie processes holding RDMA resources
- **Out-of-order event crash fix** (#1894) — startup race condition resolved
- **Failed instance retry loop prevention** (#1763) — stops cascade failures

### Multimodality
- Vision models: Qwen3.5, Kimi K2.5, Gemma 4 with vision processors
- PDF handling with text + image extraction

### API
- OpenClaw/OpenCode integration helpers
- Tailscale-friendly HTTP copying
- Improved stats and usage reporting

## Installation (all nodes)

```bash
# Install on all 4 nodes
pip3 install exo==1.0.70 --break-system-packages

# Or from Brain B (M4 Max):
for target in "ravenx@192.168.1.248" "admin@192.168.1.213" "gabegarcia@192.168.1.192"; do
    ssh $target "pip3 install exo==1.0.70 --break-system-packages 2>/dev/null || /opt/homebrew/bin/pip3 install exo==1.0.70 --break-system-packages"
done
```

## MlxRing Loader Integration

When RDMA transport is unstable, the exo-mlxring-loader recreates instances:

```bash
cd ~/Developer/exo-mlxring-loader
python3 recreate_mlxring_instance.py --model mlx-community/Qwen3.5-35B-A3B-4bit --test
```

## Cluster Startup

```bash
./scripts/start-cluster.sh
./scripts/start-cluster.sh --status
./scripts/start-cluster.sh --stop
```

## Node Configuration

| Node | IP | SSH User | Memory | exo node-id |
|------|----|----------|--------|-------------|
| Mac Studio | 192.168.1.248 | ravenx | 96 GB | m3-ultra |
| M4 Max | 192.168.1.247 | ravenx | 128 GB | m4-max-128 |
| M1 Max | 192.168.1.213 | admin | 64 GB | m1-max-64 |
| M3 | 192.168.1.192 | gabegarcia | 24 GB | m3-24 |

## Transport Priority

1. RDMA over TB5 (120 Gbps) — Mac Studio <-> M4 Max
2. RDMA over TB4 (40 Gbps) — M1 Max, M3 links
3. MlxRing fallback — when RDMA is unstable
4. HTTP over Ethernet (1 Gbps) — always-on fallback

## ANE Compensation

TB4 nodes use ANE INT8 quantization to effectively double TB4 bandwidth:
- Quantize FP16 -> INT8 on ANE before transfer (~0.1ms)
- Transfer at 2x effective rate
- Dequantize on receiver ANE (~0.1ms)
- Net: TB4 with ANE = ~8 GB/s effective (vs 4 GB/s raw)

## Source Repos
- exo: https://github.com/exo-explore/exo/releases/tag/v1.0.70
- MlxRing loader: https://github.com/DeadByDawn101/exo-mlxring-loader
- ANE: https://github.com/DeadByDawn101/ANE
