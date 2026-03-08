# STAR PLATINUM CLUSTER ARCHITECTURE (v0)

## Node roles
- **M4 Max (control + core):** OpenClaw runtime, Qwen core inference, scheduler
- **ANE worker (same host initially):** training/benchmark jobs via ANE private APIs
- **Cloud model mesh:** Sonnet/Codex/Grok/Gemini/MiniMax fallback and heavy reasoning
- **TB4 link layer (next):** high-throughput checkpoint and batch transfer path

## Routing contract
1. Default all routine inference to local Qwen core
2. Route ANE-compatible jobs to `ane_worker`
3. Route high-context/high-reasoning tasks to hosted fallback chain
4. On local failure/timeout, auto-fallback to hosted

## ANE integration points
- compile cache keyed by graph signature
- run queue for train/eval jobs
- metrics collection (`step_ms`, `util_pct`, `cpu_fallback_pct`)

## TB4 plan (phased)
- **Phase A:** software transport (shared memory + framed TCP over TB4 network)
- **Phase B:** DMA-aware transport with memory registration semantics
- **Phase C:** experimental RDMA-like queue pair model over TB4 PCIe tunnels

## Security + reliability
- Treat ANE private API as experimental plane
- Keep production path on Qwen/cloud while ANE matures
- Version pinning for macOS/Xcode/SDK
- Strong fallback guarantees on scheduler
