# Star Platinum Cluster — Phase 1 Bringup Guide

## Prerequisites

- All 4 ring nodes physically connected via Thunderbolt cables:
  - M4 Max → M3 (TB5→TB4)
  - M4 Max → M2 Pro (TB5→TB4)
  - M3 → iMac Pro (TB4→TB3)
  - M2 Pro → iMac Pro (TB4→TB3)
- Beast on Ethernet/Tailscale (NOT on TB ring — TB2 incompatible)
- macOS updated to latest version on all nodes
- Internet access for initial setup (brew, npm, git)

## Transport mode

**This cluster uses TCP over Thunderbolt (40 Gbps), NOT RDMA.**

Apple's RDMA over Thunderbolt requires:
- macOS 26.2 or later
- Thunderbolt 5 on BOTH ends of each cable
- `rdma_ctl enable` in Recovery mode

Your cluster has only one TB5 node (M4 Max). The M3, M2 Pro, and iMac Pro have TB4/TB3. RDMA needs TB5↔TB5, so TCP over Thunderbolt is the correct transport.

This still gives you 40 Gbps per link — 40× faster than Gigabit Ethernet. exo's pipeline parallel and topology-aware placement work fully over TCP.

## Step-by-step

### 1. Run setup on each node

SSH into each Mac (or sit at the keyboard) and run:

```bash
# Option A: Run directly from GitHub
curl -fsSL https://raw.githubusercontent.com/DeadByDawn101/star-platinum-cluster/main/scripts/phase1_setup.sh | bash

# Option B: Clone and run
git clone https://github.com/DeadByDawn101/star-platinum-cluster
cd star-platinum-cluster
bash scripts/phase1_setup.sh
```

Run this on ALL FOUR nodes:
1. M4 Max (brain)
2. M3 (ANE worker)
3. M2 Pro (ANE node)
4. iMac Pro (control)

The script installs: Homebrew, uv, node, rust nightly, macmon (Apple Silicon only), Xcode CLI tools, exo, ANE repo (Apple Silicon only), and configures Thunderbolt networking.

### 2. Start exo on each node

On each Mac, in a separate terminal:

```bash
cd ~/Projects/exo
uv run exo
```

exo starts on port 52415 and begins mDNS peer discovery automatically. Nodes find each other within a few seconds.

### 3. Verify the cluster

On the M4 Max (brain), run:

```bash
cd ~/Projects/star-platinum-cluster
bash scripts/phase1_verify.sh
```

Or open `http://localhost:52415` in a browser on any node. The dashboard should show all 4 nodes with their memory and connection status.

### 4. Load a test model

In the exo dashboard or via API:

```bash
# Small test model (fits on M4 Max alone)
curl http://localhost:52415/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama-3.2-3b",
    "messages": [{"role": "user", "content": "Hello from the Star Platinum cluster!"}],
    "max_tokens": 50
  }'
```

For a model that spans multiple nodes:

```bash
# Qwen 32B — will shard across nodes proportional to memory
curl http://localhost:52415/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5-32b-instruct",
    "messages": [{"role": "user", "content": "What is the Star Platinum cluster?"}],
    "max_tokens": 200
  }'
```

exo automatically downloads, shards, and distributes the model.

### 5. Verify multi-node operation

In the dashboard at `http://localhost:52415`:
- **Cluster view** should show 4 nodes with memory bars
- **Model view** should show shard distribution across nodes
- Check that inference tokens/sec improves vs single-node

## Node-specific notes

### M4 Max (brain)
- Largest memory (128 GB) — gets the majority of model layers
- Only TB5 node — fastest individual link (120 Gbps to its ports, but peers cap at 40)
- Primary exo master candidate (elected automatically)

### M3 (ANE worker)
- 24 GB — gets ~12% of layers in a 4-node split
- 2 TB SSD — good for model cache (`EXO_MODELS_DIR` can point here)
- Only 2 TB4 ports — one to M4 Max, one to iMac Pro

### M2 Pro (ANE node)
- 16 GB — smallest shard (~8% of layers)
- 3 TB4 ports — one to M4 Max, one to iMac Pro, one spare
- 500 GB SSD — limited model cache

### iMac Pro (control)
- Intel Xeon — no ANE, Vega 56 GPU only
- 32 GB — gets ~16% of layers
- 4 TB3 ports — most ports in the ring, two used
- Runs exo dashboard for cluster monitoring
- NOT an Apple Silicon node — cannot use MLX Apple Silicon optimizations

## Troubleshooting

### Nodes don't see each other
- Check cables are connected and TB link is active: `system_profiler SPThunderboltDataType`
- Run the TB network config: `sudo bash ~/Projects/exo/tmp/set_rdma_network_config.sh`
- Verify Thunderbolt Bridge is disabled: `networksetup -listnetworkserviceorder`
- Check firewall: `sudo /usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate`

### Model download fails
- Check disk space: `df -h`
- Set model directory to M3's 2TB drive: `EXO_MODELS_DIR=/path/to/shared/models uv run exo`
- For offline mode: `EXO_OFFLINE=true uv run exo`

### iMac Pro issues
- The iMac Pro runs Intel macOS — some MLX features may not be available
- If exo fails to start, check that the macOS version supports the required Python/MLX versions
- Vega 56 Metal compute should still work for GPU-side operations

### Performance seems slow
- Check which transport exo is using (TCP vs RDMA) in the dashboard
- Verify TB link speed: `networksetup -getMedia "Thunderbolt 1"` or similar
- For multi-node models, pipeline parallel has inherent per-token latency overhead
- Single-node inference on M4 Max (128 GB) will be faster for models that fit in memory
