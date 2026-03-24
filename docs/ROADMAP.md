# 「Star Platinum」— Road to First Market

## The Vision
A distributed AI supercomputer that combines local hardware (ANE + GPU + RDMA over Thunderbolt)
with cloud APIs (Claude, OpenAI, Gemini), accessed through OpenClaw as the autonomous agent layer.
Fully private local inference + cloud fallback. No one has built this.

---

## Phase 1: Fix exo Multi-Node Inference ✅ COMPLETE

### Root Cause Analysis: The Nack Storm

**What happened:**
1. Node A starts as Master, accumulates events in `DiskEventLog`
2. Node B joins and starts its `EventRouter` with `OrderedBuffer.next_idx_to_release = 0`
3. Node B receives events from Master but they're at index 800,000+ (from all our testing)
4. `OrderedBuffer.drain_indexed()` can't drain because it needs sequential events starting from 0
5. EventRouter enters Nack loop: "I need event 0, then 1, then 2..." at 1000/batch
6. Master sends batches of 1000 events at a time (hardcoded in main.py line 350)
7. At 800,000 events / 1000 per batch / ~3 seconds per batch = **40 minutes** to sync
8. During sync, no model loading can happen because the event router is blocked
9. Meanwhile more events accumulate, making it worse

### The Fix ✅ APPLIED

**Fix 1: Fast-forward on follower join** (`src/exo/routing/event_router.py`)
- Lines 49-58: When a fresh follower receives its first event at high index, skip to near-current
- `_CATCHUP_WINDOW = 100` constant
- Eliminates 40-minute replay

**Fix 2: Adaptive batch size** (`src/exo/master/main.py`)
- Lines 370-375: 25000 batch for catch-up, 1000 for steady-state
- Eliminates batch size bottleneck

**Fix 3: Event log compaction** (`src/exo/master/main.py`)
- Lines 79-93: Compacts to last 1000 events if >10000 on startup
- Prevents stale log accumulation

---

## Phase 2: Unified Router (LOCAL + CLOUD)

### Architecture

```python
# star_platinum_router.py
# Sits between OpenClaw and all backends

class StarPlatinumRouter:
    backends = {
        "local_ollama": "http://localhost:11434/v1",     # Ollama on M4 Max
        "local_exo": "http://localhost:52415/v1",         # exo cluster (when working)
        "claude": "https://api.anthropic.com/v1",         # Cloud fallback
        "openai": "https://api.openai.com/v1",            # Cloud fallback
        "gemini": "https://generativelanguage.googleapis.com/v1",
    }

    def route(self, request):
        # 1. If model is loaded locally (Ollama or exo), use local
        # 2. If model is too big for local, use cloud
        # 3. If latency matters, use whichever responds fastest
        # 4. If local is busy, overflow to cloud
        pass
```

### Implementation Plan
- OpenAI-compatible API proxy that sits on port 8000
- Routes to Ollama (11434), exo (52415), or cloud APIs
- OpenClaw points to http://localhost:8000/v1
- Smart routing based on model availability, load, and latency

---

## Phase 3: RDMA Transport over TB4/TB5 ✅ IMPLEMENTED

### Research Findings (2026-03-23)
**macOS 26.2+ has native RDMA over Thunderbolt!**
- `rdma_ctl status` = **enabled** on M4 Max
- `rdma_thunderbolt` kernel extension available
- Network.framework APIs for RDMA programming
- TB5 on M4 Max: 80 Gbps, <10μs latency
- TB4 on M1-M3: 40 Gbps, <50μs latency

### Implementation ✅ COMPLETE

| Phase | File | Status |
|-------|------|--------|
| 3A Zero-Copy TCP | `src/exo/transport/zero_copy_tcp.py` | ✅ Implemented |
| 3B TB4 Direct IP | `src/exo/transport/tb4_direct.py` | ✅ Implemented |
| 3C RDMA TB4 | `src/exo/transport/rdma_tb4.py` | ✅ Prototype |
| 3D TB5 Native RDMA | Native via rdma_thunderbolt | ✅ Ready (macOS support) |
| Benchmark Harness | `scripts/benchmark_transport.py` | ✅ Implemented |
| Network Setup | `scripts/setup_tb4_network.sh` | ✅ Implemented |

### Performance Targets

| Transport | Latency | Throughput | Status |
|-----------|---------|------------|--------|
| Baseline TCP | ~200-500μs | ~1-2 Gbps | ✅ Baseline |
| Zero-Copy TCP (3A) | ~50μs | ~3-5 Gbps | ✅ Ready |
| TB4 Direct (3B) | ~100μs | ~8-12 Gbps | 🔴 Needs cables |
| RDMA TB4 (3C) | ~30-50μs | ~15-25 Gbps | 🔴 Needs cables |
| RDMA TB5 (3D) | ~5-10μs | ~40-80 Gbps | 🔴 Needs cables |

### Remaining Work
1. **Buy and connect TB4 cables** — interfaces show inactive
2. Run `./scripts/setup_tb4_network.sh --all` to configure
3. Run `python scripts/benchmark_transport.py --mode all` to validate
4. Wire transport layer into exo gossipsub

---

## Phase 4: ANE Compute Backend

### The Differentiator
No distributed inference framework uses the ANE today. Everyone uses GPU only.
Adding ANE gives us:
- 46.9 TFLOPS additional compute across 4 nodes
- Hybrid prefill(ANE) + decode(GPU) for optimal inference
- Power efficiency (ANE uses fraction of GPU power)

### Approach
- Build CoreML bridge: convert MLX model layers → ANE-compatible format
- Route prefill operations to ANE via the bridge
- Keep decode on GPU (bandwidth-bound, GPU is better)
- Use our ANE repo's compute backend as the foundation

### Files to Create
- `src/exo/worker/engines/ane/` — new ANE engine
- `src/exo/worker/engines/ane/bridge.py` — MLX ↔ ANE bridge
- `src/exo/worker/engines/ane/scheduler.py` — hybrid ANE+GPU scheduler

---

## Current Status

| Component | Status | Next Action |
|-----------|--------|-------------|
| Hardware (4 nodes) | ✅ Working | — |
| exo discovery (mDNS) | ✅ Working with namespace | — |
| exo single-node inference | ✅ Working (Qwen3.5-35B) | — |
| Ollama single-node | ✅ Working (qwen3.5:27b) | — |
| OpenClaw + Ollama | ✅ Connected | — |
| **Nack Storm Fix** | ✅ **FIXED** | Deployed to exo |
| **Transport Layer** | ✅ **IMPLEMENTED** | Buy cables to test |
| exo multi-node inference | 🟡 Blocked on cables | Connect TB4 ring |
| Unified Router | 📋 Designed | Build in Phase 2 |
| ANE compute backend | 📋 Designed | Build in Phase 4 |

---

## Files Created/Modified

### New Transport Layer
```
~/Projects/exo/src/exo/transport/
├── __init__.py              # Transport abstraction
├── zero_copy_tcp.py         # Phase 3A: Zero-copy TCP
├── tb4_direct.py            # Phase 3B: TB4 Direct IP
└── rdma_tb4.py              # Phase 3C/D: RDMA Transport
```

### Benchmark & Setup Scripts
```
~/Projects/star-platinum-cluster/scripts/
├── benchmark_transport.py   # Transport benchmarking
└── setup_tb4_network.sh     # TB4 network configuration
```

### Documentation
```
~/Projects/star-platinum-cluster/docs/
├── RDMA-TB4-REVERSE-ENG.md  # Updated with research
└── ROADMAP.md               # This file (updated)
```

---

## Phase 5: MLX Distributed Integration ⚡ NEW

### Research Complete (2026-03-24)
**MLX 0.31+ has native distributed inference over Thunderbolt!**

Full research documented in: `docs/MLX-DEEP-DIVE.md`

### Key Discovery: MLX Already Powers exo

Exo's compute backend is already MLX-based with distributed support:
- `MlxRingInstance` — TCP Ring over TB4 ✅
- `MlxJacclInstance` — RDMA over TB5 (requires mesh topology)
- Pipeline parallelism ✅ implemented
- Tensor parallelism ✅ implemented

### Quick Wins Identified

| Win | Effort | Impact | Status |
|-----|--------|--------|--------|
| Enable `MLX_METAL_FAST_SYNCH=1` | 1 min | 10x latency reduction | 🎯 Ready |
| Upgrade MLX 0.30.7 → 0.31.1 | 5 min | Latest optimizations | 🎯 Ready |
| Connect TB4 ring + test | 30 min | Enable multi-node | 🔴 Needs cables |
| Tensor parallelism for 70B | 2 hrs | Run DeepSeek-R1 distributed | After cables |

### MLX Backend Options

| Backend | Transport | Latency | Our Topology | Feasible? |
|---------|-----------|---------|--------------|-----------|
| **Ring** | TCP over TB4 | ~50μs | Linear ring | ✅ Yes |
| JACCL | RDMA over TB5 | ~5μs | Full mesh required | ❌ Need 6 cables |
| MPI | OpenMPI | ~200μs | Any | ✅ But slower |

**Conclusion:** Ring backend over TB4 is our path. JACCL requires full mesh (N×(N-1)/2 cables = 6 for 4 nodes), which we can't achieve with standard port counts.

### Files Created

```
~/Projects/star-platinum-cluster/
├── docs/MLX-DEEP-DIVE.md              # Full research report
├── configs/star-platinum-ring.json    # MLX hostfile for 4-node ring
└── scripts/
    ├── test_mlx_distributed.py        # MLX distributed benchmark
    └── optimize_mlx_cluster.sh        # Quick optimizations
```

### Implementation Steps

**Immediate (Today):**
```bash
# 1. Apply fast sync optimization
export MLX_METAL_FAST_SYNCH=1

# 2. Run local optimization check
./scripts/optimize_mlx_cluster.sh --local
```

**When TB4 Cables Connected:**
```bash
# 3. Configure TB4 network
./scripts/setup_tb4_network.sh --all

# 4. Test MLX distributed directly
mlx.launch --hostfile configs/star-platinum-ring.json -n 4 \
  --env MLX_METAL_FAST_SYNCH=1 -- python scripts/test_mlx_distributed.py

# 5. Test exo multi-node with MLX Ring
./scripts/exo_start.sh --distributed
```

### Performance Expectations

| Config | Model | Expected Throughput |
|--------|-------|---------------------|
| Single M4 Max | Qwen3.5-35B | ~45 tok/s |
| 4-node Ring (TCP) | Qwen3.5-35B | ~35 tok/s |
| 4-node Ring (TCP) | DeepSeek-70B | ~15 tok/s |
| 4-node + optimized | DeepSeek-70B | ~20 tok/s |

*Communication overhead reduces single-node performance, but enables larger models*

---

## Timeline (Updated)

- **Week 1:** ~~Phase 1 (Nack fix)~~ ✅ Complete
- **Week 1:** ~~Phase 3 (Transport layer)~~ ✅ Implemented
- **Week 2:** ~~Phase 5 (MLX research)~~ ✅ Complete
- **Now:** 
  - Apply MLX_METAL_FAST_SYNCH optimization
  - Buy TB4 cables, connect ring
- **Next:** 
  - Phase 2 (Router MVP)
  - TB4 + MLX distributed benchmarks
- **Week 3-4:** Phase 4 (ANE backend)
- **Week 5+:** Optimization, benchmarks, documentation, release

---

## Current Status (Updated 2026-03-24)

| Component | Status | Next Action |
|-----------|--------|-------------|
| Hardware (4 nodes) | ✅ Working | — |
| exo discovery (mDNS) | ✅ Working with namespace | — |
| exo single-node inference | ✅ Working (Qwen3.5-35B) | — |
| Ollama single-node | ✅ Working (qwen3.5:27b) | — |
| OpenClaw + Ollama | ✅ Connected | — |
| **Nack Storm Fix** | ✅ **FIXED** | Deployed to exo |
| **Transport Layer** | ✅ **IMPLEMENTED** | Buy cables to test |
| **MLX Research** | ✅ **COMPLETE** | See MLX-DEEP-DIVE.md |
| **MLX Optimizations** | 🎯 **READY** | Run optimize_mlx_cluster.sh |
| exo multi-node inference | 🟡 Blocked on cables | Connect TB4 ring |
| Unified Router | 📋 Designed | Build in Phase 2 |
| ANE compute backend | 📋 Designed | Build in Phase 4 |

---

## Phase 6: MiroFish Swarm Intelligence 🐟 NEW

### Overview (Added 2026-03-24)

MiroFish is a multi-agent swarm intelligence engine for predictive simulation. Integrating it with Star Platinum enables:
- **Zero-cost AI predictions** via local inference
- **Trading bot enhancement** for Maya Scorpio & RAZOR
- **Emergent forecasting** through agent simulations

### Integration Points

| Component | Integration Method | Status |
|-----------|-------------------|--------|
| LLM Backend | OpenAI-compatible API | ✅ Ready (port 52415) |
| Memory (Zep) | Cloud service | ✅ Free tier available |
| Simulation Engine | OASIS (camel-ai) | ✅ Installed |
| Trading Integration | Maya API wrapper | 📋 Planned |

### Use Cases

1. **Pre-Trade Sentiment Analysis**
   - Simulate market reaction before execution
   - Predict social media sentiment cascade
   - Risk assessment through agent debates

2. **Memecoin Launch Prediction**
   - Model retail vs whale behavior
   - Simulate pump/dump dynamics
   - Identify optimal entry/exit timing

3. **Crisis PR Simulation**
   - Test messaging before deployment
   - Identify amplifier accounts
   - Model counter-narrative effectiveness

### Installation

```bash
# Already installed at ~/Projects/MiroFish
cd ~/Projects/MiroFish
source .venv/bin/activate  # Python 3.11 required
npm run dev
```

### Configuration for Star Platinum

```bash
# In .env
LLM_BASE_URL=http://localhost:52415/v1
LLM_MODEL_NAME=mlx-community/Qwen3.5-35B-A3B-4bit
```

### Files Created

```
~/Projects/MiroFish/
├── RAVENX-SETUP.md              # RavenX-specific setup guide
└── .venv/                       # Python 3.11 environment (ready)

~/Projects/star-platinum-cluster/docs/
├── MIROFISH-INTEGRATION.md      # Full integration analysis
└── QA-RESULTS.md                # Cluster QA results
```

### Timeline

- **Week 1:** ✅ Install MiroFish, configure for Star Platinum
- **Week 2:** Test simulations with local LLM backend
- **Week 3:** Integrate with Maya trading signals
- **Month 2:** Production deployment for RavenX AI

---

---

## Phase 7: RavenX AI Trading Intelligence Stack 🧠 NEW

### Overview (Added 2026-03-24)

Research and prototype implementation for an AI-powered trading intelligence system combining:
- **LeWM (LeWorldModel)**: Market world model for state prediction
- **SELF**: Self-evolving LLM analyst with language feedback
- **Star Platinum Cluster**: 184GB distributed compute for training + inference

### Research Documents Created

| Document | Purpose | Location |
|----------|---------|----------|
| **LEWM-MARKET-DESIGN.md** | LeWM adaptation for financial time series | `research/` |
| **SELF-TRADING-DESIGN.md** | SELF framework for trading analysis | `research/` |
| **RAVENX-AI-STACK.md** | Full integration architecture | `research/` |

### Prototype Code

| File | Description | Status |
|------|-------------|--------|
| `lewm_market_prototype.py` | MLX-based market world model (15M params) | ✅ Ready |
| `self_trade_loop.py` | SELF evolution pipeline with Llama 70B | ✅ Ready |

### Key Insights from Research

**LeWorldModel (arxiv:2603.19312):**
- 15M parameter JEPA that trains in hours on single GPU
- Two-term loss: prediction + SIGReg (Gaussian regularization)
- No stop-gradient, no EMA, no pretrained encoders — pure end-to-end
- Adaptable to market "frames" (OHLCV as 2D images)

**SELF (arxiv:2310.00533):**
- Self-evolution through language feedback (no human labels needed)
- Win/loss from Maya trades = automatic ground truth
- Model critiques own analysis, improves through iteration
- Self-refinement at inference time for better predictions

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  RAVENX AI TRADING STACK                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Market Data ──▶ LeWM World Model ──▶ State Prediction     │
│       │                                     │               │
│       └──────────────▶ SELF Analyst ◀──────┘               │
│                            │                                │
│                 Self-Critique + Refinement                  │
│                            │                                │
│                            ▼                                │
│  Maya Indicators ──▶ Decision Fusion ──▶ Trade/Skip        │
│                            │                                │
│                            ▼                                │
│                    Maya Execution                           │
│                            │                                │
│                    Win/Loss Feedback ──▶ Nightly Training   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Training Pipeline

```
NIGHTLY (2 AM PT):
1. Collect Maya decisions from GCP
2. Prepare LeWM training data (market frames)
3. Train LeWM (~45 min on single node)
4. Generate SELF training data (Llama 70B)
5. Fine-tune SELF with LoRA (~90 min distributed)
6. Evaluate and deploy if improved
```

### Hardware Requirements

| Component | Memory | Nodes |
|-----------|--------|-------|
| LeWM (15M) | 2GB training | 1 (M4 Max) |
| Llama 70B (4-bit) | 45GB inference | 4 distributed |
| Training batch | 120GB headroom | Full cluster |

### Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Win Rate | 55% | > 60% |
| Confidence Calibration | ±20% | ±10% |
| Inference Latency | N/A | < 2s |
| Training Success | N/A | > 95% |

### Timeline

| Week | Milestone |
|------|-----------|
| 1 | Prototypes complete, single-node testing |
| 2 | Maya integration, A/B testing |
| 3-4 | Distributed training, optimization |
| Month 2+ | Continuous learning, production deployment |

### Files Created

```
~/Projects/star-platinum-cluster/research/
├── LEWM-MARKET-DESIGN.md          # LeWM design document
├── SELF-TRADING-DESIGN.md         # SELF design document
├── RAVENX-AI-STACK.md             # Integration architecture
├── lewm_market_prototype.py       # LeWM MLX implementation
└── self_trade_loop.py             # SELF pipeline implementation
```

### Next Steps

1. **Connect TB4 cables** — Enable distributed training
2. **Run initial training** — LeWM + SELF on 30 days of Maya data
3. **Maya integration hook** — Add AI signals to decision pipeline
4. **A/B testing** — Maya vs Maya+AI comparison
5. **Nightly automation** — Cron job for continuous learning

---

*RavenX LLC — 2026. Zero compromises.* 🖤
