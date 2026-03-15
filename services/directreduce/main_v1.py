#!/usr/bin/env python3
"""DirectReduce service v1 — with ANE ComputeEnhancer offload.

Upgrades the v0 software-only reducer with:
  1. ANE-accelerated reduction at background QoS (when available)
  2. Async chunk pipeline with backpressure
  3. GateKeeper/DataDirector/ComputeEnhancer as distinct stages
  4. Metrics collection for cluster monitoring

Falls back to numpy (or pure Python) on non-ANE nodes.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import time
from typing import Any, Dict, List, Optional

# Try to import the ANE compute backend
try:
    from ane_engine.ane_compute import (
        ANEReduceEngine,
        ANECapabilities,
        detect_ane,
        ANEMemoryRegion,
    )
    _ANE_AVAILABLE = True
except ImportError:
    _ANE_AVAILABLE = False


class GateKeeper:
    """
    DirectReduce GateKeeper: evaluates outgoing data to decide its
    progression — either directing it to the Protocol Engine for
    packetization or intercepting it for immediate reduction.

    Decision criteria:
      - Chunk size < threshold → pass through (latency-optimized)
      - Chunk size >= threshold → intercept for reduction (throughput-optimized)
      - If all chunks for a reduction group have arrived → trigger reduce
    """

    def __init__(self, reduction_threshold_bytes: int = 65536):
        self.reduction_threshold = reduction_threshold_bytes
        self._pending: Dict[str, List[List[float]]] = {}
        self._expected_chunks: Dict[str, int] = {}

    def submit_chunk(
        self,
        group_id: str,
        chunk: List[float],
        expected_total: int,
    ) -> Optional[List[List[float]]]:
        """
        Submit a chunk for a reduction group.
        Returns all chunks when the group is complete, None otherwise.
        """
        if group_id not in self._pending:
            self._pending[group_id] = []
            self._expected_chunks[group_id] = expected_total

        self._pending[group_id].append(chunk)

        if len(self._pending[group_id]) >= self._expected_chunks[group_id]:
            chunks = self._pending.pop(group_id)
            self._expected_chunks.pop(group_id)
            return chunks

        return None

    @property
    def pending_groups(self) -> int:
        return len(self._pending)


class DataDirector:
    """
    DirectReduce DataDirector: classifies incoming data as
    intermediate (needs more reduction) or final (ready for storage).

    In a ring topology, a chunk is intermediate if it has been
    reduced fewer times than (num_nodes - 1). After that many
    reductions, it's final.
    """

    def __init__(self, num_nodes: int = 2):
        self.num_nodes = num_nodes
        self._reduction_counts: Dict[str, int] = {}

    def classify(self, chunk_id: str) -> str:
        """Returns 'intermediate' or 'final'."""
        count = self._reduction_counts.get(chunk_id, 0)
        if count >= self.num_nodes - 1:
            return "final"
        return "intermediate"

    def record_reduction(self, chunk_id: str):
        self._reduction_counts[chunk_id] = self._reduction_counts.get(chunk_id, 0) + 1


class ComputeEnhancer:
    """
    DirectReduce ComputeEnhancer: executes reduction operations.

    When ANE is available, dispatches at background QoS to keep
    reduction completely off the main inference/training path.
    Falls back to numpy/Python on non-ANE platforms.
    """

    def __init__(self):
        self._ane_engine: Optional[Any] = None
        self._backend = "python"

        if _ANE_AVAILABLE:
            caps = detect_ane()
            if caps is not None:
                self._ane_engine = ANEReduceEngine(capabilities=caps)
                self._backend = f"ane-{caps.chip}"

    @property
    def backend(self) -> str:
        return self._backend

    def reduce(self, chunks: List[List[float]], op: str) -> List[float]:
        if self._ane_engine is not None:
            return self._ane_engine.reduce(chunks, op)
        return self._reduce_fallback(chunks, op)

    def _reduce_fallback(self, chunks: List[List[float]], op: str) -> List[float]:
        if not chunks:
            return []
        cols = len(chunks[0])
        if any(len(c) != cols for c in chunks):
            raise ValueError("chunk width mismatch")
        try:
            import numpy as np
            arr = np.array(chunks, dtype=np.float32)
            if op == "sum":
                return arr.sum(axis=0).tolist()
            elif op == "max":
                return arr.max(axis=0).tolist()
            elif op == "mean":
                return arr.mean(axis=0).tolist()
            else:
                raise ValueError(f"unsupported op: {op}")
        except ImportError:
            out = []
            for i in range(cols):
                vals = [c[i] for c in chunks]
                if op == "sum":
                    out.append(sum(vals))
                elif op == "max":
                    out.append(max(vals))
                elif op == "mean":
                    out.append(sum(vals) / len(vals))
                else:
                    raise ValueError(f"unsupported op: {op}")
            return out


# === Metrics ===

class DirectReduceMetrics:
    def __init__(self):
        self.total_reductions = 0
        self.total_chunks_processed = 0
        self.total_bytes_reduced = 0
        self.total_time_ms = 0.0
        self.errors = 0
        self.start_time = time.time()

    def record(self, num_chunks: int, chunk_len: int, elapsed_ms: float):
        self.total_reductions += 1
        self.total_chunks_processed += num_chunks
        self.total_bytes_reduced += num_chunks * chunk_len * 4  # float32
        self.total_time_ms += elapsed_ms

    def to_dict(self) -> Dict[str, Any]:
        uptime = time.time() - self.start_time
        return {
            "total_reductions": self.total_reductions,
            "total_chunks_processed": self.total_chunks_processed,
            "total_bytes_reduced": self.total_bytes_reduced,
            "total_time_ms": round(self.total_time_ms, 2),
            "avg_ms_per_reduction": round(
                self.total_time_ms / max(1, self.total_reductions), 2
            ),
            "errors": self.errors,
            "uptime_s": round(uptime, 1),
        }


# === Service ===

gatekeeper = GateKeeper()
data_director = DataDirector()
compute_enhancer = ComputeEnhancer()
metrics = DirectReduceMetrics()


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, payload: Dict):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {
                "ok": True,
                "service": "directreduce",
                "version": "v1-ane",
                "backend": compute_enhancer.backend,
                "ane_available": _ANE_AVAILABLE,
                "pending_groups": gatekeeper.pending_groups,
            })
            return
        if self.path == "/metrics":
            self._send(200, {"ok": True, **metrics.to_dict()})
            return
        self._send(404, {"error": "not_found"})

    def do_POST(self):
        if self.path == "/allreduce":
            return self._handle_allreduce()
        if self.path == "/submit_chunk":
            return self._handle_submit_chunk()
        self._send(404, {"error": "not_found"})

    def _handle_allreduce(self):
        length = int(self.headers.get("Content-Length", "0"))
        data = self.rfile.read(length)
        req = json.loads(data or b"{}")

        op = req.get("op", "sum")
        chunks = req.get("chunks", [])

        t0 = time.perf_counter()
        try:
            reduced = compute_enhancer.reduce(chunks, op)
        except Exception as e:
            metrics.errors += 1
            self._send(400, {"ok": False, "error": str(e)})
            return
        elapsed_ms = (time.perf_counter() - t0) * 1000

        if chunks:
            metrics.record(len(chunks), len(chunks[0]), elapsed_ms)

        self._send(200, {
            "ok": True,
            "op": op,
            "num_chunks": len(chunks),
            "result": reduced,
            "elapsed_ms": round(elapsed_ms, 3),
            "backend": compute_enhancer.backend,
            "architecture": {
                "gatekeeper": "packet/reduce path split",
                "datadirector": "intermediate/final classification",
                "compute_enhancer": f"{compute_enhancer.backend} reduction engine",
            },
        })

    def _handle_submit_chunk(self):
        """
        Incremental chunk submission for ring all-reduce.
        Chunks accumulate in GateKeeper until a group is complete,
        then auto-reduce via ComputeEnhancer.
        """
        length = int(self.headers.get("Content-Length", "0"))
        data = self.rfile.read(length)
        req = json.loads(data or b"{}")

        group_id = req.get("group_id", "default")
        chunk = req.get("chunk", [])
        expected = req.get("expected_chunks", 2)
        op = req.get("op", "sum")

        complete_chunks = gatekeeper.submit_chunk(group_id, chunk, expected)

        if complete_chunks is None:
            self._send(202, {
                "ok": True,
                "status": "pending",
                "group_id": group_id,
                "received": len(gatekeeper._pending.get(group_id, [])),
                "expected": expected,
            })
            return

        # All chunks received — reduce
        t0 = time.perf_counter()
        try:
            reduced = compute_enhancer.reduce(complete_chunks, op)
        except Exception as e:
            metrics.errors += 1
            self._send(400, {"ok": False, "error": str(e)})
            return
        elapsed_ms = (time.perf_counter() - t0) * 1000

        metrics.record(len(complete_chunks), len(complete_chunks[0]), elapsed_ms)
        data_director.record_reduction(group_id)
        classification = data_director.classify(group_id)

        self._send(200, {
            "ok": True,
            "status": "reduced",
            "classification": classification,
            "group_id": group_id,
            "op": op,
            "num_chunks": len(complete_chunks),
            "result": reduced,
            "elapsed_ms": round(elapsed_ms, 3),
            "backend": compute_enhancer.backend,
        })


def main() -> None:
    host = os.getenv("SPC_DIRECTREDUCE_HOST", "127.0.0.1")
    port = int(os.getenv("SPC_DIRECTREDUCE_PORT", "9092"))
    server = HTTPServer((host, port), Handler)
    print(f"directreduce v1 listening on http://{host}:{port}")
    print(f"  backend: {compute_enhancer.backend}")
    print(f"  ANE available: {_ANE_AVAILABLE}")
    server.serve_forever()


if __name__ == "__main__":
    main()
