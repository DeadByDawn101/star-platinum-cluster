#!/usr/bin/env python3
"""
MLX Distributed Test Script for Star Platinum Cluster

Usage:
  # Local test (single process)
  python test_mlx_distributed.py

  # Multi-node test via mlx.launch
  mlx.launch --hostfile configs/star-platinum-ring.json -n 4 test_mlx_distributed.py

  # With fast sync enabled
  mlx.launch --hostfile configs/star-platinum-ring.json -n 4 \
    --env MLX_METAL_FAST_SYNCH=1 -- python test_mlx_distributed.py
"""

import os
import sys
import time
from dataclasses import dataclass

import mlx.core as mx

@dataclass
class BenchmarkResult:
    operation: str
    size_mb: float
    latency_ms: float
    throughput_gbps: float

def benchmark_all_sum(world: mx.distributed.Group, size: int, iterations: int = 10) -> BenchmarkResult:
    """Benchmark all_sum operation."""
    x = mx.random.uniform(shape=(size,))
    mx.eval(x)
    
    # Warmup
    for _ in range(3):
        y = mx.distributed.all_sum(x)
        mx.eval(y)
    
    # Benchmark
    start = time.perf_counter()
    for _ in range(iterations):
        y = mx.distributed.all_sum(x)
        mx.eval(y)
    elapsed = time.perf_counter() - start
    
    size_mb = (size * 4) / (1024 * 1024)  # float32 = 4 bytes
    latency_ms = (elapsed / iterations) * 1000
    throughput_gbps = (size_mb * 8 * 2 * (world.size() - 1)) / (elapsed / iterations) / 1000
    
    return BenchmarkResult("all_sum", size_mb, latency_ms, throughput_gbps)

def benchmark_all_gather(world: mx.distributed.Group, size: int, iterations: int = 10) -> BenchmarkResult:
    """Benchmark all_gather operation."""
    x = mx.random.uniform(shape=(size,))
    mx.eval(x)
    
    # Warmup
    for _ in range(3):
        y = mx.distributed.all_gather(x)
        mx.eval(y)
    
    # Benchmark
    start = time.perf_counter()
    for _ in range(iterations):
        y = mx.distributed.all_gather(x)
        mx.eval(y)
    elapsed = time.perf_counter() - start
    
    size_mb = (size * 4) / (1024 * 1024)
    latency_ms = (elapsed / iterations) * 1000
    throughput_gbps = (size_mb * 8 * (world.size() - 1)) / (elapsed / iterations) / 1000
    
    return BenchmarkResult("all_gather", size_mb, latency_ms, throughput_gbps)

def main():
    # Initialize distributed
    world = mx.distributed.init()
    rank = world.rank()
    size = world.size()
    
    print(f"[Rank {rank}/{size}] MLX Distributed Test")
    print(f"[Rank {rank}/{size}] MLX version: {mx.__version__}")
    print(f"[Rank {rank}/{size}] Backend: {os.environ.get('MLX_BACKEND', 'auto')}")
    print(f"[Rank {rank}/{size}] Fast sync: {os.environ.get('MLX_METAL_FAST_SYNCH', '0')}")
    
    if size == 1:
        print("\n⚠️  Running in single-node mode. Use mlx.launch for multi-node testing.")
        print("Example: mlx.launch --hostfile configs/star-platinum-ring.json -n 4 test_mlx_distributed.py\n")
    
    # Test sizes: 1KB, 1MB, 10MB, 100MB
    test_sizes = [
        (256, "1KB"),
        (256 * 1024, "1MB"),
        (2560 * 1024, "10MB"),
        (25600 * 1024, "100MB"),
    ]
    
    print(f"\n{'='*60}")
    print(f" MLX Distributed Benchmark - {size} nodes")
    print(f"{'='*60}\n")
    
    results = []
    
    for num_elements, label in test_sizes:
        # all_sum
        result = benchmark_all_sum(world, num_elements)
        results.append((label, result))
        if rank == 0:
            print(f"all_sum  {label:>6}: {result.latency_ms:8.2f}ms, {result.throughput_gbps:6.2f} Gbps")
        
        # all_gather
        result = benchmark_all_gather(world, num_elements)
        results.append((label, result))
        if rank == 0:
            print(f"all_gather {label:>4}: {result.latency_ms:8.2f}ms, {result.throughput_gbps:6.2f} Gbps")
        
        if rank == 0:
            print()
    
    # Verify correctness
    if rank == 0:
        print(f"{'='*60}")
        print(f" Correctness Check")
        print(f"{'='*60}\n")
    
    # Each rank contributes its rank value
    local = mx.array([float(rank)])
    summed = mx.distributed.all_sum(local)
    mx.eval(summed)
    
    expected = sum(range(size))  # 0 + 1 + 2 + ... + (size-1)
    actual = float(summed[0])
    
    if abs(actual - expected) < 0.01:
        print(f"[Rank {rank}/{size}] ✅ all_sum correct: {actual} == {expected}")
    else:
        print(f"[Rank {rank}/{size}] ❌ all_sum FAILED: {actual} != {expected}")
    
    # all_gather check
    gathered = mx.distributed.all_gather(local)
    mx.eval(gathered)
    
    expected_gathered = list(range(size))
    actual_gathered = [float(x) for x in gathered]
    
    if actual_gathered == expected_gathered:
        print(f"[Rank {rank}/{size}] ✅ all_gather correct: {actual_gathered}")
    else:
        print(f"[Rank {rank}/{size}] ❌ all_gather FAILED: {actual_gathered} != {expected_gathered}")
    
    if rank == 0:
        print(f"\n{'='*60}")
        print(f" Done!")
        print(f"{'='*60}")

if __name__ == "__main__":
    main()
