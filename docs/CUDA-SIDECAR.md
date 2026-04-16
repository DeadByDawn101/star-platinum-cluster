# CUDA Sidecar

How the RTX 3090 fits into Star Platinum without being a brain, a ring node, or a first-class exo peer. It's a **compute endpoint** — the cluster routes specific workloads to it via device-class rules.

---

## Why a sidecar, not a node

A ring node on Star Platinum is an Apple Silicon device with unified memory, ANE, Metal, and RDMA over Thunderbolt. The 3090 has none of those things:

- No unified memory — 24 GB discrete VRAM, PCIe round-trip to host.
- No ANE, no Metal — CUDA and CUDA only.
- Not on the DMA ring — it's a PCIe device behind Thunderbolt, not a DMA peer of the Apple nodes.
- No macOS display output via TinyGPU — compute-only.

Trying to force the 3090 into the ring as an equal peer would either require a huge translation layer (Metal ↔ CUDA) or break assumptions across exo, DirectReduce, and TurboQuant. Instead, it lives outside the ring as a **sidecar attached to Brain A**, and the router dispatches CUDA-class work to it.

This mirrors how datacenter clusters handle heterogeneous accelerators: you don't pretend a TPU is a GPU, you route TPU-appropriate work to TPUs.

---

## Hardware

| Component | Spec |
|---|---|
| GPU | NVIDIA RTX 3090 (Ampere, GA102) |
| VRAM | 24 GB GDDR6X |
| CUDA cores | 10,496 |
| FP16 (tensor) | ~71 TFLOPS |
| TDP | 350 W |
| Enclosure | Sonnet Breakaway Box 850 T5 |
| Enclosure PSU | 850 W |
| Host link | Thunderbolt 5 (80 Gbps) → attached to `m3-ultra` |
| Driver | TinyGPU (Apple-signed DriverKit extension) |

**Connection:** one TB5 cable from the M3 Ultra (Brain A) directly to the Sonnet Breakaway. No hub, no daisy chain. TB5 bandwidth is generous for a 3090 — the card can't saturate PCIe 4.0 x16 on its best day, and TB5 delivers ~PCIe 4.0 x4 equivalent over the wire.

**Power:** the 3090 draws up to 350W under load. The Sonnet 850W PSU has ~500W of headroom, which is important because Ampere has transient power spikes well above TDP. Don't try this with a 650W enclosure.

---

## Driver setup: TinyGPU

TinyCorp's Apple-signed DriverKit extension. **No SIP disabling, no kext workarounds** — this went through Apple's standard notarization.

Requirements:
- macOS 12.1 or later (you're on Tahoe — fine)
- USB4 or Thunderbolt 3/4/5 port (you have TB5 — fine)
- NVIDIA Ampere or newer (3090 is Ampere — fine)
- Docker Desktop for Mac with ≥8 GB RAM and ≥20 GB disk allocated

### Install on M3 Ultra (Brain A)

```bash
# 1. Docker Desktop — set Resources to 8GB+ RAM, 20GB+ disk
open -a "Docker Desktop"

# 2. Clone and build TinyGPU
cd ~/src
git clone https://github.com/tinygrad/tinygpu
cd tinygpu
make nvidia
# Builds TinyGPU.kext inside Docker. ~5 minutes on M4-class silicon.

# 3. Install the app + driver extension
open TinyGPU.app
# Approve the DriverKit extension in:
#   System Settings → Privacy & Security → toggle "Allow"
# This is a one-time step. Driver autoloads on reboot.

# 4. Plug in Sonnet + 3090, power on, verify the card is seen
tinygpu-cli list
# Expected: NVIDIA GeForce RTX 3090 (24GB) — ready
```

### Sanity test

```bash
# Quick CUDA sanity check from tinygrad
DEBUG=2 NV=1 python3 -c "
from tinygrad import Tensor, Device
print('Device:', Device.DEFAULT)
t = Tensor.rand(1024, 1024).realize()
print('OK:', t.shape)
"
```

If that prints `Device: NV` and returns a shape, the card is live.

### Known limitations (as of April 2026)

- **Compute only.** No display output from the 3090 on macOS — which is fine for our use case, the cluster is headless.
- **Docker dependency for NVCC.** NVIDIA's compiler toolchain runs inside Docker Desktop. TinyGPU invokes NVCC in the container as needed.
- **No CUDA-X libraries.** cuBLAS, cuDNN, NCCL etc. not natively available. You get raw CUDA + whatever inference engines ship their own kernels (vLLM, exllama, llama.cpp).
- **Single-GPU.** If you add a second 3090 later, current TinyGPU docs suggest it works but hasn't been widely tested with NCCL.

---

## Software stack on the sidecar

| Layer | Component | What it does |
|---|---|---|
| L4 | **Device router** | `configs/routing.yaml` — sends CUDA-class work here |
| L3 | **vLLM** | Primary LLM serving engine (OpenAI-compatible API) |
| L3 | **exllama-v2** | Alternative for GPTQ/EXL2 models |
| L3 | **llama.cpp (CUDA)** | GGUF serving when model format dictates |
| L3 | **ComfyUI** | Primary image-gen (SDXL, FLUX, SD3, Wan) |
| L3 | **stable-diffusion-webui (forge)** | Alternative image-gen — gradio UI, plugin ecosystem |
| L2 | **CUDA runtime** | Via TinyGPU driver |
| L1 | **TinyGPU DriverKit** | Apple-signed, connects the 3090 over TB5 |
| L0 | **RTX 3090** | 24 GB VRAM, Ampere tensor cores |

**We do not run training on the sidecar by default.** 24 GB VRAM is enough for QLoRA on models up to ~13B, but anything bigger needs Brain B's 128 GB unified memory. Fine-tune routing goes to Brain B unless the model is CUDA-native and large enough that Brain B can't batch it efficiently.

---

## Image generation on the sidecar

The 3090 is a strong image-gen card — 24 GB VRAM comfortably fits SDXL, FLUX, SD3, and most video-gen models (Wan, HunyuanVideo at lower resolutions). Running image-gen on the sidecar keeps it off the Apple ring, where MLX-based diffusion (DiffusionKit, mflux) is still catching up on speed and feature parity with the CUDA ecosystem.

### ComfyUI — primary

Graph-based, scriptable, and what the image-gen community builds nodes for.

```bash
# ComfyUI with CUDA via TinyGPU
docker run -d --name comfyui-3090 \
  --device /dev/tinygpu0 \
  -p 8188:8188 \
  -v ~/comfyui/models:/app/models \
  -v ~/comfyui/output:/app/output \
  -v ~/comfyui/workflows:/app/user/default/workflows \
  yanwk/comfyui-boot:cu124-slim
```

Hook ComfyUI into `hermit-purple-studio` (your ComfyUI-based frontend) by pointing the studio's backend at `http://m3-ultra.beardie-ph.ts.net:8188`. The Ultra already hosts the studio UI; the 3090 does the denoising.

### stable-diffusion-webui (forge) — alternative

Use when you want the gradio plugin ecosystem (ControlNet variants, community extensions, regional prompter, etc.).

```bash
docker run -d --name sdwebui-3090 \
  --device /dev/tinygpu0 \
  -p 7860:7860 \
  -v ~/sdwebui/models:/stable-diffusion-webui/models \
  -v ~/sdwebui/outputs:/stable-diffusion-webui/outputs \
  ashleykza/stable-diffusion-webui-forge:latest
```

### Concurrent image + LLM serving

You can have ComfyUI warm on the 3090 alongside vLLM — the image model stays resident in one VRAM slice, the LLM in another. Be honest about the budget:

| Workload | Typical VRAM at steady state |
|---|---|
| vLLM + 13B AWQ model | ~10 GB |
| ComfyUI + SDXL | ~8 GB |
| ComfyUI + FLUX.1-dev | ~12 GB |
| ComfyUI + HunyuanVideo | ~20 GB (barely fits) |

vLLM + SDXL coexist fine on a 24 GB card. vLLM + FLUX is tight. Anything + HunyuanVideo means you're unloading the LLM. The router enforces these constraints via per-class VRAM budgets:

```yaml
# configs/routing.yaml (image-gen additions)
classes:
  cuda:
    nodes: [rtx-3090]
    attached_to: m3-ultra
    vram_gb: 24
    budget:
      llm: 12       # vLLM / exllama / llama.cpp share this pool
      image: 10     # ComfyUI / sdwebui share this pool
      reserve: 2    # allocator headroom
    backends:
      vllm:
        endpoint: http://m3-ultra.beardie-ph.ts.net:8000/v1
        max_model_size_b: 34
        supports: [awq, gptq, safetensors-pytorch]
      exllama:
        endpoint: http://m3-ultra.beardie-ph.ts.net:8001/v1
        supports: [exl2, gptq]
      llama_cpp:
        endpoint: http://m3-ultra.beardie-ph.ts.net:8002/v1
        supports: [gguf]
      comfyui:
        endpoint: http://m3-ultra.beardie-ph.ts.net:8188
        supports: [sdxl, flux, sd3, wan]
      sdwebui:
        endpoint: http://m3-ultra.beardie-ph.ts.net:7860
        supports: [sdxl, sd15, controlnet]

routing:
  rules:
    - when: task == "image-generate"
      route: cuda.comfyui
      fallback: cuda.sdwebui
    - when: task == "image-generate" and model.family == "controlnet-plugin"
      route: cuda.sdwebui
    - when: task == "video-generate"
      route: cuda.comfyui
      require: vram_free_gb >= 18    # unload LLM first if needed
```

### When to unload

Video-gen or FLUX at max resolution will need the whole card. The router enforces this via the `require: vram_free_gb >= 18` clause — if the 3090 is under that threshold, the router first sends an unload hint to vLLM, waits for confirmation, then dispatches the image job. This adds 2-5s to the first video-gen request but keeps everything stable.

For bursty workflows where you're iterating on an image: warm ComfyUI, accept the LLM eviction, iterate, then let the LLM reload on its next request. For steady LLM serving with occasional images: keep vLLM resident, use SDXL (which fits), skip FLUX until you need it.

---

## Device-class routing

The sidecar lives inside the routing policy as the sole `cuda` class. Jobs route to it when:

- **Model format is CUDA-native:** GGUF, AWQ, GPTQ, EXL2, or raw PyTorch safetensors with CUDA kernels (FA3, flash-attn, Triton).
- **Backend requires NVCC:** vLLM, exllama, llama.cpp with CUDA build, stable-diffusion-webui.
- **Explicit route:** requester asks for `device: cuda` in the API.

Jobs do **not** route to it when:
- Model is MLX format — stays on Apple Silicon.
- Training job >13B — goes to Brain B.
- Agent tool-loop — handoff cost eats the throughput gain.

### Example routing fragment

```yaml
# configs/routing.yaml
classes:
  cuda:
    nodes: [rtx-3090]
    attached_to: m3-ultra
    backends:
      vllm:
        endpoint: http://m3-ultra.beardie-ph.ts.net:8000/v1
        max_model_size_b: 34      # 3090 24GB fits ~34B at Q4
        supports: [awq, gptq, safetensors-pytorch]
      exllama:
        endpoint: http://m3-ultra.beardie-ph.ts.net:8001/v1
        supports: [exl2, gptq]
      llama_cpp:
        endpoint: http://m3-ultra.beardie-ph.ts.net:8002/v1
        supports: [gguf]

routing:
  rules:
    - when: model.format == "awq"
      route: cuda.vllm
    - when: model.format == "gptq"
      route: cuda.vllm
    - when: model.format == "exl2"
      route: cuda.exllama
    - when: model.format == "gguf" and model.params_b <= 34
      route: cuda.llama_cpp
      priority: 60      # lower than Apple ring default
    - when: model.format == "mlx"
      route: metal       # never sidecar
```

Note the GGUF rule has `priority: 60` — GGUF *can* run on the ring via llama.cpp-metal, and for small models the ring is faster end-to-end because you skip the TB5 round-trip. CUDA wins for medium GGUFs where the 3090 tensor cores dominate.

---

## Why run services on Brain A, not the sidecar directly

vLLM, exllama, and llama.cpp run as **local services on the M3 Ultra**, each pinned to the 3090 via the TinyGPU device handle. The sidecar never exposes a separate host — it's just a compute device that the M3 Ultra drives.

**Why:**
- One host, one address book. The router hits `m3-ultra.beardie-ph.ts.net:8000` (vLLM) and the Ultra talks to the card.
- No separate OS to maintain on the sidecar. The 3090 is compute only.
- Monitoring, auth, rate limits all live in one place.
- If the TB5 cable yanks, the Ultra sees a device-detach event and marks the `cuda` class down cleanly.

### Service bring-up sketch

```bash
# vLLM — primary serving engine
docker run -d --name vllm-3090 \
  --device /dev/tinygpu0 \
  -p 8000:8000 \
  -v ~/models:/models \
  vllm/vllm-openai:latest \
  --model /models/your-model-awq \
  --quantization awq \
  --max-model-len 8192

# exllama-v2 — EXL2 lane
docker run -d --name exllama-3090 \
  --device /dev/tinygpu0 \
  -p 8001:8000 \
  turboderp/exllamav2-server \
  --model /models/your-model-exl2

# llama.cpp — GGUF lane
docker run -d --name llama-cuda \
  --device /dev/tinygpu0 \
  -p 8002:8080 \
  ghcr.io/ggerganov/llama.cpp:server-cuda \
  -m /models/your-model.gguf \
  -c 8192 --n-gpu-layers 999
```

All three run simultaneously — they don't fight over VRAM at rest, only when actively serving. The router picks the right one per request. When one engine is serving, the others yield VRAM via CUDA's default allocator behavior; if that becomes a problem in practice, pin VRAM budgets per container.

---

## Health and monitoring

### What to watch

| Metric | Good | Bad |
|---|---|---|
| TB5 link status | `connected` | `detached` → reload driver or reseat cable |
| VRAM free | > 2 GB headroom at rest | OOM risk with multi-engine |
| Temperature | < 78°C | > 84°C — enclosure airflow problem |
| Power draw | < 400 W | > 450 W sustained — check PSU |
| Request latency (p99) | < 1.5× Apple ring latency for same model | > 3× — TB5 bottleneck, retry smaller batches |

### Detect a down sidecar

```bash
# Brain A periodic health check (runs every 5s)
tinygpu-cli status | grep -q ready || {
  echo "sidecar down — failing cuda class"
  curl -X POST http://localhost:52416/routing/class/cuda/down
}
```

When `cuda` class is marked down, router rules fall through to ring/Metal if possible. If the model is CUDA-only (AWQ, EXL2), request returns 503 with `"cuda_unavailable": true`.

---

## When to upgrade the sidecar

Signals you're outgrowing the 3090:

- **Sustained queue depth > 5** on vLLM during normal use — add a second 3090.
- **Models you want to run don't fit in 24 GB at Q4** — go 5090 (32 GB) or dual 3090.
- **Training jobs routinely take > 2 hours** — Brain B is doing training; the sidecar isn't for training.
- **You're constantly evicting LLM for image-gen or vice versa** — the 24 GB is oversubscribed. A 5090 (32 GB) buys you LLM + FLUX coexisting without juggling.
- **Video generation (HunyuanVideo, Wan 2.1 at full res) becomes a primary workload** — video eats everything. Dedicate a card, or go 5090.

The Sonnet Breakaway holds one triple-wide card. For two 3090s you need either a second Breakaway (TB5-chained into the M3 Ultra's second TB5 controller) or a bigger enclosure.

A single 5090 simplifies things: 32 GB VRAM covers most 70B-at-4bit + KV, and Ada Lovelace tensor cores are much faster than Ampere. Cost per useful token is roughly a wash with dual 3090 but you keep the topology simple.

---

## Related documents

- [`DUAL-BRAIN.md`](./DUAL-BRAIN.md) — why the sidecar attaches to Brain A specifically
- [`ARCHITECTURE.md`](./ARCHITECTURE.md) — full cluster topology
- [`HARDWARE-REGISTRY.md`](./HARDWARE-REGISTRY.md) — per-node specs, retired nodes
- [`../configs/routing.yaml`](../configs/routing.yaml) — live routing policy
- [`../configs/supercomputer.yaml`](../configs/supercomputer.yaml) — cluster topology
- [`../scripts/cuda_sidecar_bringup.sh`](../scripts/cuda_sidecar_bringup.sh) — automation script

### External

- [TinyGPU](https://github.com/tinygrad/tinygpu) — Apple-signed DriverKit extension
- [tinygrad](https://github.com/tinygrad/tinygrad) — compute framework
- [vLLM](https://github.com/vllm-project/vllm) — inference server
- [exllamav2](https://github.com/turboderp/exllamav2) — EXL2 runtime
- [Sonnet Breakaway Box 850 T5](https://www.sonnettech.com/product/breakaway-box-850-t5.html) — enclosure
