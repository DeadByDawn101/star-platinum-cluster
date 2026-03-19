# 「Star Platinum」— Road to First Market

## The Vision
A distributed AI supercomputer that combines local hardware (ANE + GPU + RDMA over Thunderbolt)
with cloud APIs (Claude, OpenAI, Gemini), accessed through OpenClaw as the autonomous agent layer.
Fully private local inference + cloud fallback. No one has built this.

---

## Phase 1: Fix exo Multi-Node Inference (THE BLOCKER)

### Root Cause Analysis: The Nack Storm

**What happens:**
1. Node A starts as Master, accumulates events in `DiskEventLog`
2. Node B joins and starts its `EventRouter` with `OrderedBuffer.next_idx_to_release = 0`
3. Node B receives events from Master but they're at index 800,000+ (from all our testing)
4. `OrderedBuffer.drain_indexed()` can't drain because it needs sequential events starting from 0
5. EventRouter enters Nack loop: "I need event 0, then 1, then 2..." at 1000/batch
6. Master sends batches of 1000 events at a time (hardcoded in main.py line 350)
7. At 800,000 events / 1000 per batch / ~3 seconds per batch = **40 minutes** to sync
8. During sync, no model loading can happen because the event router is blocked
9. Meanwhile more events accumulate, making it worse

**The hardcoded bottleneck** (src/exo/master/main.py:350):
```python
end = min(command.since_idx + 1000, len(self._event_log))
```

### The Fix (3 parts):

**Fix 1: Allow followers to skip to latest state (snapshot sync)**

When a new follower joins, instead of replaying the entire event history,
send a state snapshot + only recent events. The follower doesn't need
event 0 from three days ago — it needs the current cluster state.

File: `src/exo/routing/event_router.py`
In `_run_ext_in()`, when `next_idx_to_release` is 0 and we receive events
at a high index, jump `next_idx_to_release` to `received_idx - CATCHUP_WINDOW`
where CATCHUP_WINDOW is something like 100.

```python
# In EventRouter._run_ext_in(), after receiving an event:
if self.event_buffer.next_idx_to_release == 0 and event.origin_idx > 100:
    # Skip to near-current state instead of replaying entire history
    self.event_buffer.next_idx_to_release = max(0, event.origin_idx - 100)
    logger.info(f"Fast-forwarding event buffer to {self.event_buffer.next_idx_to_release}")
```

**Fix 2: Increase batch size for catch-up**

File: `src/exo/master/main.py` line 350
Change from 1000 to 25000 for catch-up, 1000 for steady-state:

```python
# Adaptive batch size: large for catch-up, small for steady-state
gap = len(self._event_log) - command.since_idx
batch_size = 25000 if gap > 5000 else 1000
end = min(command.since_idx + batch_size, len(self._event_log))
```

**Fix 3: Add event log rotation/compaction on startup**

File: `src/exo/master/main.py` in `__init__` or startup
On Master startup, if event log has >10K events, compact to last 1000:

```python
# On master startup, compact event log if too large
if len(self._event_log) > 10000:
    logger.info(f"Compacting event log from {len(self._event_log)} to last 1000 events")
    # Only keep last 1000 events
    recent = list(self._event_log.read_range(len(self._event_log) - 1000, len(self._event_log)))
    self._event_log.close()
    self._event_log = DiskEventLog(EXO_EVENT_LOG_DIR / "master")
    for event in recent:
        self._event_log.append(event)
```

### How to Apply

On the M4 Max:
```bash
cd ~/Projects/exo
# Apply the patches (I'll provide exact patches)
git pull origin main
# Edit the files
# Restart exo on all nodes
```

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

## Phase 3: RDMA Transport over TB4

### The Challenge
TB4 doesn't natively support RDMA. TB5 does via the Apple RDMA framework.
But we can build a zero-copy transport that approaches RDMA performance.

### Approach
- Use `mmap` + shared memory regions over Thunderbolt IP
- Custom transport layer for MLX's `mx.distributed` backend
- Replace the gossipsub TCP transport with direct memory-mapped transfers
- Target: <50μs latency per tensor transfer (vs ~200μs TCP today)

### Files to Modify
- `rust/networking/src/swarm.rs` — transport layer
- `src/exo/worker/engines/mlx/auto_parallel.py` — distributed ops
- New: `src/exo/transport/rdma_tb4.py` — custom transport

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
| exo multi-node inference | ❌ Nack storm | Apply Phase 1 fix |
| Unified Router | 📋 Designed | Build in Phase 2 |
| RDMA over TB4 | 📋 Designed | Build in Phase 3 |
| ANE compute backend | 📋 Designed | Build in Phase 4 |
| Big Mouth (2017 MBP) | ⏸️ Tabled | Resume after cluster |
| iMac Pro Tahoe | ⏸️ Waiting | After 2017 MBP test |

---

## Timeline

- **Week 1:** Phase 1 (Nack fix) + Phase 2 (Router MVP)
- **Week 2-3:** Phase 3 (RDMA transport)
- **Week 4-6:** Phase 4 (ANE backend)
- **Week 7+:** Optimization, benchmarks, documentation, release
