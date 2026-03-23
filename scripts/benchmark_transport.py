#!/usr/bin/env python3
"""
Star Platinum Cluster - Transport Benchmark Harness

Benchmarks different transport layers for tensor transfer:
1. Baseline TCP (current exo default)
2. Zero-Copy TCP (Phase 3A)
3. TB4 Direct IP with jumbo frames (Phase 3B)
4. RDMA over TB4/TB5 (Phase 3C/3D)

Measures:
- Latency (μs): time to complete a transfer
- Throughput (Gbps): sustained data rate
- CPU overhead: CPU time spent in transfer

Usage:
    python benchmark_transport.py --mode all --size 100 --iterations 100
    python benchmark_transport.py --mode tcp --size 10 --iterations 50
    python benchmark_transport.py --remote-host 169.254.1.2 --remote-port 52416

RavenX LLC - Star Platinum Cluster
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import resource
import socket
import statistics
import struct
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

# Add exo to path
EXO_ROOT = Path(__file__).parent.parent.parent / "exo" / "src"
sys.path.insert(0, str(EXO_ROOT))


@dataclass
class BenchmarkResult:
    """Results from a single benchmark run."""
    transport_name: str
    tensor_size_mb: float
    num_iterations: int
    latencies_us: List[float]
    bytes_transferred: int
    cpu_time_us: float
    
    @property
    def avg_latency_us(self) -> float:
        return statistics.mean(self.latencies_us)
    
    @property
    def min_latency_us(self) -> float:
        return min(self.latencies_us)
    
    @property
    def max_latency_us(self) -> float:
        return max(self.latencies_us)
    
    @property
    def p50_latency_us(self) -> float:
        return statistics.median(self.latencies_us)
    
    @property
    def p99_latency_us(self) -> float:
        sorted_lat = sorted(self.latencies_us)
        idx = int(len(sorted_lat) * 0.99)
        return sorted_lat[idx]
    
    @property
    def stddev_latency_us(self) -> float:
        if len(self.latencies_us) < 2:
            return 0.0
        return statistics.stdev(self.latencies_us)
    
    @property
    def throughput_gbps(self) -> float:
        total_us = sum(self.latencies_us)
        if total_us == 0:
            return 0.0
        # bytes * 8 (bits) / us = Mbps, / 1000 = Gbps
        return (self.bytes_transferred * 8) / (total_us * 1000)
    
    @property
    def cpu_overhead_percent(self) -> float:
        total_us = sum(self.latencies_us)
        if total_us == 0:
            return 0.0
        return (self.cpu_time_us / total_us) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "transport": self.transport_name,
            "tensor_size_mb": self.tensor_size_mb,
            "num_iterations": self.num_iterations,
            "avg_latency_us": round(self.avg_latency_us, 2),
            "min_latency_us": round(self.min_latency_us, 2),
            "max_latency_us": round(self.max_latency_us, 2),
            "p50_latency_us": round(self.p50_latency_us, 2),
            "p99_latency_us": round(self.p99_latency_us, 2),
            "stddev_latency_us": round(self.stddev_latency_us, 2),
            "throughput_gbps": round(self.throughput_gbps, 3),
            "cpu_overhead_percent": round(self.cpu_overhead_percent, 2),
            "bytes_transferred": self.bytes_transferred,
        }


def get_cpu_time_us() -> float:
    """Get current process CPU time in microseconds."""
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return (usage.ru_utime + usage.ru_stime) * 1_000_000


def create_test_tensor(size_mb: float) -> Tuple[bytes, Tuple[int, ...], str]:
    """Create a random tensor for testing."""
    num_elements = int(size_mb * 1024 * 1024 / 4)  # float32 = 4 bytes
    data = np.random.randn(num_elements).astype(np.float32)
    return data.tobytes(), (num_elements,), "float32"


# =============================================================================
# Baseline TCP Benchmark
# =============================================================================

async def benchmark_baseline_tcp(
    size_mb: float,
    iterations: int,
    remote_host: Optional[str] = None,
    remote_port: int = 52417,
) -> BenchmarkResult:
    """
    Benchmark baseline TCP transport (current exo default).
    """
    print(f"🔷 Benchmarking Baseline TCP ({size_mb}MB x {iterations} iterations)")
    
    data, shape, dtype = create_test_tensor(size_mb)
    latencies: List[float] = []
    
    cpu_start = get_cpu_time_us()
    
    if remote_host:
        # Remote benchmark
        latencies = await _benchmark_tcp_remote(data, shape, dtype, iterations, remote_host, remote_port)
    else:
        # Local loopback benchmark
        latencies = await _benchmark_tcp_loopback(data, shape, dtype, iterations)
    
    cpu_end = get_cpu_time_us()
    
    return BenchmarkResult(
        transport_name="baseline_tcp",
        tensor_size_mb=size_mb,
        num_iterations=iterations,
        latencies_us=latencies,
        bytes_transferred=len(data) * iterations * 2,  # send + recv
        cpu_time_us=cpu_end - cpu_start,
    )


async def _benchmark_tcp_loopback(
    data: bytes,
    shape: Tuple[int, ...],
    dtype: str,
    iterations: int,
) -> List[float]:
    """Run TCP benchmark on localhost."""
    latencies = []
    port = 52450
    
    # Create server
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind(("127.0.0.1", port))
    server_sock.listen(1)
    server_sock.setblocking(False)
    
    # Connect client
    client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_sock.setblocking(False)
    
    loop = asyncio.get_event_loop()
    
    try:
        await loop.sock_connect(client_sock, ("127.0.0.1", port))
    except BlockingIOError:
        pass
    
    conn_sock, _ = await loop.sock_accept(server_sock)
    conn_sock.setblocking(False)
    
    # Header
    header = json.dumps({"shape": list(shape), "dtype": dtype}).encode()
    
    for i in range(iterations):
        start_ns = time.perf_counter_ns()
        
        # Send header + data
        packet = struct.pack("!I", len(header)) + header + struct.pack("!Q", len(data)) + data
        await loop.sock_sendall(client_sock, packet)
        
        # Receive on server side
        header_len_bytes = await loop.sock_recv(conn_sock, 4)
        h_len = struct.unpack("!I", header_len_bytes)[0]
        
        h_data = b""
        while len(h_data) < h_len:
            h_data += await loop.sock_recv(conn_sock, h_len - len(h_data))
        
        data_len_bytes = await loop.sock_recv(conn_sock, 8)
        d_len = struct.unpack("!Q", data_len_bytes)[0]
        
        received = b""
        while len(received) < d_len:
            received += await loop.sock_recv(conn_sock, min(d_len - len(received), 65536))
        
        elapsed_ns = time.perf_counter_ns() - start_ns
        latencies.append(elapsed_ns / 1000.0)
    
    client_sock.close()
    conn_sock.close()
    server_sock.close()
    
    return latencies


async def _benchmark_tcp_remote(
    data: bytes,
    shape: Tuple[int, ...],
    dtype: str,
    iterations: int,
    remote_host: str,
    remote_port: int,
) -> List[float]:
    """Run TCP benchmark against remote host."""
    latencies = []
    
    # Connect to remote
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setblocking(False)
    
    loop = asyncio.get_event_loop()
    await loop.sock_connect(sock, (remote_host, remote_port))
    
    header = json.dumps({"shape": list(shape), "dtype": dtype}).encode()
    
    for i in range(iterations):
        start_ns = time.perf_counter_ns()
        
        packet = struct.pack("!I", len(header)) + header + struct.pack("!Q", len(data)) + data
        await loop.sock_sendall(sock, packet)
        
        # Wait for ack (4 bytes)
        ack = await loop.sock_recv(sock, 4)
        
        elapsed_ns = time.perf_counter_ns() - start_ns
        latencies.append(elapsed_ns / 1000.0)
    
    sock.close()
    return latencies


# =============================================================================
# Zero-Copy TCP Benchmark
# =============================================================================

async def benchmark_zero_copy_tcp(
    size_mb: float,
    iterations: int,
    remote_host: Optional[str] = None,
    remote_port: int = 52418,
) -> BenchmarkResult:
    """
    Benchmark zero-copy TCP transport (Phase 3A).
    """
    print(f"🔷 Benchmarking Zero-Copy TCP ({size_mb}MB x {iterations} iterations)")
    
    try:
        from exo.transport.zero_copy_tcp import ZeroCopyTCPTransport
    except ImportError as e:
        print(f"  ⚠️  Zero-copy transport not available: {e}")
        return _empty_result("zero_copy_tcp", size_mb, iterations)
    
    data, shape, dtype = create_test_tensor(size_mb)
    latencies: List[float] = []
    
    cpu_start = get_cpu_time_us()
    
    # Use local benchmark
    transport = ZeroCopyTCPTransport(port=52451)
    await transport.start_server()
    
    loop = asyncio.get_event_loop()
    client_sock = await transport.connect("127.0.0.1", 52451)
    server_sock, _ = await loop.sock_accept(transport._server_socket)
    transport._optimize_socket(server_sock)
    server_sock.setblocking(False)
    
    for i in range(iterations):
        send_us = await transport.send_tensor_data(client_sock, data, shape, dtype)
        _, _, _, recv_us = await transport.recv_tensor_data(server_sock)
        latencies.append(send_us + recv_us)
    
    cpu_end = get_cpu_time_us()
    
    client_sock.close()
    server_sock.close()
    await transport.close()
    
    return BenchmarkResult(
        transport_name="zero_copy_tcp",
        tensor_size_mb=size_mb,
        num_iterations=iterations,
        latencies_us=latencies,
        bytes_transferred=len(data) * iterations * 2,
        cpu_time_us=cpu_end - cpu_start,
    )


# =============================================================================
# TB4 Direct Benchmark
# =============================================================================

async def benchmark_tb4_direct(
    size_mb: float,
    iterations: int,
    remote_host: Optional[str] = None,
    remote_port: int = 52419,
) -> BenchmarkResult:
    """
    Benchmark TB4 direct transport (Phase 3B).
    """
    print(f"🔷 Benchmarking TB4 Direct ({size_mb}MB x {iterations} iterations)")
    
    try:
        from exo.transport.tb4_direct import TB4DirectTransport, discover_tb4_interfaces
    except ImportError as e:
        print(f"  ⚠️  TB4 transport not available: {e}")
        return _empty_result("tb4_direct", size_mb, iterations)
    
    # Check if TB4 interfaces exist
    interfaces = discover_tb4_interfaces()
    active_interfaces = [i for i in interfaces if i.is_active]
    
    if not active_interfaces:
        print("  ⚠️  No active TB4 interfaces (cables not connected)")
        return _empty_result("tb4_direct", size_mb, iterations)
    
    print(f"  Found {len(active_interfaces)} active TB4 interfaces")
    
    data, shape, dtype = create_test_tensor(size_mb)
    latencies: List[float] = []
    
    cpu_start = get_cpu_time_us()
    
    transport = TB4DirectTransport()
    await transport.initialize()
    
    # For now, fall back to loopback since we need peer
    # A full test would connect to another node via TB4 IP
    
    loop = asyncio.get_event_loop()
    
    # Create server on first active interface
    iface = active_interfaces[0]
    if iface.ip_address:
        server_sock = transport.create_optimized_socket()
        server_sock.bind((iface.ip_address, remote_port))
        server_sock.listen(1)
        server_sock.setblocking(False)
        
        client_sock = await transport.connect_to_peer(iface.ip_address, remote_port)
        conn_sock, _ = await loop.sock_accept(server_sock)
        conn_sock.setblocking(False)
        
        for i in range(iterations):
            send_us = await transport.send_tensor(client_sock, data, shape, dtype)
            _, _, _, recv_us = await transport.recv_tensor(conn_sock)
            latencies.append(send_us + recv_us)
        
        client_sock.close()
        conn_sock.close()
        server_sock.close()
    
    cpu_end = get_cpu_time_us()
    
    return BenchmarkResult(
        transport_name="tb4_direct",
        tensor_size_mb=size_mb,
        num_iterations=iterations,
        latencies_us=latencies if latencies else [0.0],
        bytes_transferred=len(data) * len(latencies) * 2,
        cpu_time_us=cpu_end - cpu_start,
    )


# =============================================================================
# RDMA Benchmark
# =============================================================================

async def benchmark_rdma(
    size_mb: float,
    iterations: int,
    remote_host: Optional[str] = None,
    remote_port: int = 52420,
) -> BenchmarkResult:
    """
    Benchmark RDMA transport (Phase 3C/3D).
    """
    print(f"🔷 Benchmarking RDMA over Thunderbolt ({size_mb}MB x {iterations} iterations)")
    
    try:
        from exo.transport.rdma_tb4 import RDMATB4Transport, RDMATransportStatus
    except ImportError as e:
        print(f"  ⚠️  RDMA transport not available: {e}")
        return _empty_result("rdma_tb", size_mb, iterations)
    
    transport = RDMATB4Transport()
    status = await transport.initialize()
    
    if status == RDMATransportStatus.NOT_AVAILABLE:
        print("  ⚠️  RDMA not available on this system")
        return _empty_result("rdma_tb", size_mb, iterations)
    
    if status != RDMATransportStatus.ENABLED:
        print(f"  ⚠️  RDMA status: {status.value}")
        return _empty_result("rdma_tb", size_mb, iterations)
    
    data, shape, dtype = create_test_tensor(size_mb)
    latencies: List[float] = []
    
    cpu_start = get_cpu_time_us()
    
    # RDMA benchmark requires peer connection
    # For now, measure local overhead
    for i in range(iterations):
        send_us = await transport.send_tensor("local", data, shape, dtype)
        _, _, _, recv_us = await transport.recv_tensor("local")
        latencies.append(send_us + recv_us)
    
    cpu_end = get_cpu_time_us()
    
    return BenchmarkResult(
        transport_name="rdma_tb",
        tensor_size_mb=size_mb,
        num_iterations=iterations,
        latencies_us=latencies,
        bytes_transferred=len(data) * iterations * 2,
        cpu_time_us=cpu_end - cpu_start,
    )


def _empty_result(name: str, size_mb: float, iterations: int) -> BenchmarkResult:
    """Create empty result for unavailable transport."""
    return BenchmarkResult(
        transport_name=name,
        tensor_size_mb=size_mb,
        num_iterations=0,
        latencies_us=[0.0],
        bytes_transferred=0,
        cpu_time_us=0.0,
    )


# =============================================================================
# Main
# =============================================================================

async def run_all_benchmarks(
    size_mb: float,
    iterations: int,
    remote_host: Optional[str] = None,
) -> List[BenchmarkResult]:
    """Run all transport benchmarks."""
    results = []
    
    # Baseline TCP
    result = await benchmark_baseline_tcp(size_mb, iterations, remote_host)
    results.append(result)
    
    # Zero-Copy TCP
    result = await benchmark_zero_copy_tcp(size_mb, iterations, remote_host)
    results.append(result)
    
    # TB4 Direct
    result = await benchmark_tb4_direct(size_mb, iterations, remote_host)
    results.append(result)
    
    # RDMA
    result = await benchmark_rdma(size_mb, iterations, remote_host)
    results.append(result)
    
    return results


def print_results(results: List[BenchmarkResult]) -> None:
    """Print benchmark results in a nice table."""
    print("\n" + "=" * 80)
    print("🌩️ Star Platinum Cluster - Transport Benchmark Results")
    print("=" * 80)
    
    # Header
    print(f"\n{'Transport':<20} {'Avg Lat (μs)':<15} {'P99 Lat (μs)':<15} {'Throughput':<12} {'CPU %':<10}")
    print("-" * 72)
    
    for r in results:
        if r.num_iterations == 0:
            print(f"{r.transport_name:<20} {'N/A':<15} {'N/A':<15} {'N/A':<12} {'N/A':<10}")
        else:
            print(f"{r.transport_name:<20} {r.avg_latency_us:<15.2f} {r.p99_latency_us:<15.2f} {r.throughput_gbps:<12.3f} Gbps {r.cpu_overhead_percent:<10.1f}")
    
    print("-" * 72)
    
    # Performance comparison
    baseline = next((r for r in results if r.transport_name == "baseline_tcp"), None)
    if baseline and baseline.num_iterations > 0:
        print("\n📊 Performance vs Baseline TCP:")
        for r in results:
            if r.transport_name != "baseline_tcp" and r.num_iterations > 0:
                lat_improvement = (baseline.avg_latency_us / r.avg_latency_us) if r.avg_latency_us > 0 else 0
                tput_improvement = (r.throughput_gbps / baseline.throughput_gbps) if baseline.throughput_gbps > 0 else 0
                print(f"  {r.transport_name}: {lat_improvement:.1f}x lower latency, {tput_improvement:.1f}x higher throughput")
    
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Star Platinum Cluster Transport Benchmark"
    )
    parser.add_argument(
        "--mode",
        choices=["all", "tcp", "zerocopy", "tb4", "rdma"],
        default="all",
        help="Which transport(s) to benchmark"
    )
    parser.add_argument(
        "--size",
        type=float,
        default=10.0,
        help="Tensor size in MB"
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=100,
        help="Number of iterations"
    )
    parser.add_argument(
        "--remote-host",
        type=str,
        default=None,
        help="Remote host for cross-node benchmark"
    )
    parser.add_argument(
        "--remote-port",
        type=int,
        default=52416,
        help="Remote port"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )
    
    args = parser.parse_args()
    
    async def run():
        if args.mode == "all":
            results = await run_all_benchmarks(args.size, args.iterations, args.remote_host)
        elif args.mode == "tcp":
            results = [await benchmark_baseline_tcp(args.size, args.iterations, args.remote_host)]
        elif args.mode == "zerocopy":
            results = [await benchmark_zero_copy_tcp(args.size, args.iterations, args.remote_host)]
        elif args.mode == "tb4":
            results = [await benchmark_tb4_direct(args.size, args.iterations, args.remote_host)]
        elif args.mode == "rdma":
            results = [await benchmark_rdma(args.size, args.iterations, args.remote_host)]
        else:
            results = []
        
        if args.json:
            print(json.dumps([r.to_dict() for r in results], indent=2))
        else:
            print_results(results)
    
    asyncio.run(run())


if __name__ == "__main__":
    main()
