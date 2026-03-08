#!/usr/bin/env python3
"""Quick correctness/perf harness for directreduce service."""

from __future__ import annotations
import json
import random
import time
import urllib.request


def post(url: str, payload: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def baseline_sum(chunks):
    return [sum(vals) for vals in zip(*chunks)]


def run():
    chunks = [[random.random() for _ in range(2048)] for _ in range(8)]

    t0 = time.perf_counter()
    b = baseline_sum(chunks)
    t1 = time.perf_counter()

    t2 = time.perf_counter()
    r = post("http://127.0.0.1:9092/allreduce", {"op": "sum", "chunks": chunks})
    t3 = time.perf_counter()

    ok = all(abs(x - y) < 1e-6 for x, y in zip(b, r["result"]))

    print(json.dumps({
        "correct": ok,
        "baseline_ms": (t1 - t0) * 1000,
        "directreduce_ms": (t3 - t2) * 1000,
        "num_chunks": len(chunks),
        "chunk_len": len(chunks[0]),
    }, indent=2))


if __name__ == "__main__":
    run()
