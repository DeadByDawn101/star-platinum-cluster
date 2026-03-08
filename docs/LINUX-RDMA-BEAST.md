# Linux Beast Node: RDMA Core Integration

Target upstream: https://github.com/linux-rdma/rdma-core

## Why this is critical
`rdma-core` provides the canonical Linux userspace stack for RDMA:
- `libibverbs`
- `librdmacm`
- providers + tooling (`ibv_*`, `rdma_*`)

For the RavenX beast Linux server, this becomes the foundation for:
1. Native RDMA experiments
2. TB4/RDMA-like transport prototyping parity with Linux tooling
3. Future direct integration of cluster collective offload backends

## Installation strategy (beast)

### Option A: distro packages (fast path)
```bash
sudo apt update
sudo apt install -y rdma-core ibverbs-providers librdmacm1 libibverbs1 ibverbs-utils perftest
```

### Option B: source build (control path)
```bash
git clone https://github.com/linux-rdma/rdma-core.git
cd rdma-core
bash build.sh
sudo ./build/bin/rdma-ndd --version || true
```

## Validation checklist
```bash
rdma link show
ibv_devices
ibv_devinfo
ib_write_bw -h
```

## Cluster integration points
- Add `rdma_backend` in DirectReduce service as optional backend.
- Keep software backend as default fallback.
- Route large all-reduce chunks to `rdma_backend` when beast node is healthy.

## Guardrails
- Keep this isolated on Linux beast node first.
- Do not block local Qwen core path while RDMA backend matures.
- Add health checks and timeout-based fallback to software reducer.
