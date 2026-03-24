#!/bin/bash
#
# optimize_mlx_cluster.sh - Quick optimizations for MLX distributed performance
#
# Usage:
#   ./scripts/optimize_mlx_cluster.sh [--all|--local|--check]
#
# This script applies performance optimizations for MLX distributed inference
# across the Star Platinum cluster.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check MLX version and distributed status
check_mlx() {
    log_info "Checking MLX installation..."
    
    python3 -c "
import mlx.core as mx
print(f'  MLX Version: {mx.__version__}')
print(f'  Distributed available: {mx.distributed.is_available()}')

# Check backend availability
for backend in ['ring', 'jaccl', 'mpi', 'nccl']:
    try:
        avail = mx.distributed.is_available(backend)
        status = '✅' if avail else '❌'
        print(f'  {backend} backend: {status}')
    except:
        print(f'  {backend} backend: ❌ (not supported)')
" 2>/dev/null || {
        log_error "MLX not found or import failed"
        return 1
    }
    
    log_success "MLX check complete"
}

# Apply environment optimizations
apply_env_optimizations() {
    log_info "Setting up environment optimizations..."
    
    # Create/update shell profile exports
    PROFILE_FILE="$HOME/.star_platinum_env"
    
    cat > "$PROFILE_FILE" << 'EOF'
# Star Platinum MLX Optimizations
# Source this file: source ~/.star_platinum_env

# Critical: Enable fast GPU↔CPU synchronization
# This reduces distributed communication latency by ~10x
export MLX_METAL_FAST_SYNCH=1

# Enable verbose distributed logging (useful for debugging)
# export MLX_RING_VERBOSE=1

# Set default distributed backend
export MLX_DEFAULT_BACKEND=ring

# Metal optimizations
export METAL_DEVICE_WRAPPER_TYPE=1

# Python optimizations
export PYTHONOPTIMIZE=1

# Disable Python GC during inference (optional, may help throughput)
# export PYTHONGC=0
EOF
    
    log_success "Created $PROFILE_FILE"
    log_info "To activate: source ~/.star_platinum_env"
    
    # Also apply to current session
    export MLX_METAL_FAST_SYNCH=1
    log_success "Applied MLX_METAL_FAST_SYNCH=1 to current session"
}

# Check TB4 network interfaces
check_tb4_interfaces() {
    log_info "Checking Thunderbolt interfaces..."
    
    # Find bridge interfaces (TB4)
    tb_interfaces=$(ifconfig 2>/dev/null | grep -E "^bridge[0-9]+" | cut -d: -f1 || true)
    
    if [ -z "$tb_interfaces" ]; then
        log_warn "No bridge interfaces found. TB4 cables may not be connected."
        log_info "Connect TB4 cables and run: ./scripts/setup_tb4_network.sh --all"
        return 1
    fi
    
    for iface in $tb_interfaces; do
        status=$(ifconfig "$iface" 2>/dev/null | grep -E "status: (active|inactive)" | awk '{print $2}')
        ip=$(ifconfig "$iface" 2>/dev/null | grep "inet " | awk '{print $2}' | head -1)
        
        if [ "$status" = "active" ]; then
            log_success "$iface: $status ${ip:-no IP}"
        else
            log_warn "$iface: $status ${ip:-no IP}"
        fi
    done
}

# Check RDMA availability (for JACCL)
check_rdma() {
    log_info "Checking RDMA status..."
    
    if command -v ibv_devices &>/dev/null; then
        devices=$(ibv_devices 2>/dev/null | tail -n +3 | wc -l)
        if [ "$devices" -gt 0 ]; then
            log_success "RDMA enabled with $devices device(s)"
            ibv_devices 2>/dev/null | tail -n +3 | while read -r line; do
                log_info "  $line"
            done
        else
            log_warn "RDMA enabled but no devices found"
        fi
    else
        log_warn "RDMA not available (ibv_devices not found)"
        log_info "To enable RDMA: Boot to recovery mode, run 'rdma_ctl enable'"
    fi
}

# Upgrade MLX to latest
upgrade_mlx() {
    log_info "Checking for MLX updates..."
    
    # Check if we're in a venv
    if [ -n "$VIRTUAL_ENV" ]; then
        pip_cmd="pip"
    else
        pip_cmd="pip3"
    fi
    
    current=$($pip_cmd show mlx 2>/dev/null | grep "Version:" | awk '{print $2}' || echo "not installed")
    
    log_info "Current MLX version: $current"
    log_info "Checking PyPI for latest..."
    
    latest=$($pip_cmd index versions mlx 2>/dev/null | head -1 | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" || echo "unknown")
    
    if [ "$current" != "$latest" ] && [ "$latest" != "unknown" ]; then
        log_warn "Newer version available: $latest"
        read -p "Upgrade MLX? [y/N] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            $pip_cmd install --upgrade mlx mlx-lm
            log_success "MLX upgraded to $latest"
        fi
    else
        log_success "MLX is up to date"
    fi
}

# Run basic distributed test
run_test() {
    log_info "Running local distributed test..."
    
    python3 -c "
import mlx.core as mx
import time

world = mx.distributed.init()
print(f'Rank: {world.rank()}, Size: {world.size()}')

# Quick benchmark
x = mx.random.uniform(shape=(1000000,))
mx.eval(x)

start = time.perf_counter()
for _ in range(100):
    y = mx.distributed.all_sum(x)
    mx.eval(y)
elapsed = time.perf_counter() - start

size_mb = (1000000 * 4) / (1024 * 1024)
print(f'all_sum 4MB x 100: {elapsed*1000:.1f}ms total, {elapsed*10:.2f}ms avg')
print(f'Throughput: {size_mb * 100 / elapsed:.1f} MB/s')
" 2>&1 || {
        log_error "Test failed"
        return 1
    }
    
    log_success "Local test complete"
}

# Main
main() {
    case "${1:-}" in
        --all)
            check_mlx
            apply_env_optimizations
            check_tb4_interfaces
            check_rdma
            upgrade_mlx
            run_test
            ;;
        --local)
            check_mlx
            apply_env_optimizations
            run_test
            ;;
        --check)
            check_mlx
            check_tb4_interfaces
            check_rdma
            ;;
        --upgrade)
            upgrade_mlx
            ;;
        *)
            echo "Star Platinum MLX Optimization Script"
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --all      Run all optimizations and checks"
            echo "  --local    Apply local optimizations only"
            echo "  --check    Check system status without changes"
            echo "  --upgrade  Check and upgrade MLX"
            echo ""
            echo "Quick start:"
            echo "  $0 --local"
            ;;
    esac
}

main "$@"
