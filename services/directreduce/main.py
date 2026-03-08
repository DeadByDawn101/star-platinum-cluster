#!/usr/bin/env python3
"""DirectReduce service (v0)
Software implementation of GateKeeper/DataDirector/ComputeEnhancer concepts.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from typing import Dict, List


def reduce_chunks(chunks: List[List[float]], op: str) -> List[float]:
    if not chunks:
        return []
    cols = len(chunks[0])
    if any(len(c) != cols for c in chunks):
        raise ValueError("chunk width mismatch")

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


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, payload: Dict):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            self._send(200, {"ok": True, "service": "directreduce", "mode": "software-v0"})
            return
        self._send(404, {"error": "not_found"})

    def do_POST(self):  # noqa: N802
        if self.path != "/allreduce":
            self._send(404, {"error": "not_found"})
            return

        length = int(self.headers.get("Content-Length", "0"))
        data = self.rfile.read(length)
        req = json.loads(data or b"{}")

        op = req.get("op", "sum")
        chunks = req.get("chunks", [])

        try:
            reduced = reduce_chunks(chunks, op)
        except Exception as e:
            self._send(400, {"ok": False, "error": str(e)})
            return

        self._send(200, {
            "ok": True,
            "op": op,
            "num_chunks": len(chunks),
            "result": reduced,
            "architecture": {
                "gatekeeper": "packet/reduce path split (logical)",
                "datadirector": "intermediate/final chunk classification (logical)",
                "compute_enhancer": "software reduction engine",
            },
        })


def main() -> None:
    server = HTTPServer(("127.0.0.1", 9092), Handler)
    print("directreduce listening on http://127.0.0.1:9092")
    server.serve_forever()


if __name__ == "__main__":
    main()
