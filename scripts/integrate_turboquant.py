#!/usr/bin/env python3
"""
integrate_turboquant.py — Install TurboQuant + Grove on all Star Platinum nodes.

Configures:
1. TurboQuant KV cache compression patched into exo
2. Persistent KV cache directory on each node
3. Tiered cache: GPU → SSD (per node)
4. Grove exo bridge for autoresearch

Usage:
    python3 scripts/integrate_turboquant.py
    python3 scripts/integrate_turboquant.py --check-only
    python3 scripts/integrate_turboquant.py --apply-patch
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

# Project paths
TURBOQUANT_PATH = Path("/Users/ravenx/Projects/turboquant-mlx")
GROVE_PATH = Path("/Users/ravenx/Projects/grove-mlx")
CLUSTER_PATH = Path("/Users/ravenx/Projects/star-platinum-cluster")

# Cluster nodes
NODES = {
    "brain": {"host": "localhost", "user": "ravenx", "ip": "192.168.1.151", "chip": "M4 Max", "ram": 128},
    "m3": {"host": "Node1s-MacBook-Pro.local", "user": "node1", "ip": "192.168.1.158", "chip": "M3", "ram": 24},
    "m2pro": {"host": "macbook-m2.local", "user": "admon", "ip": "192.168.1.177", "chip": "M2 Pro", "ram": 16},
    "m1pro": {"host": "Node-3-m1pro.local", "user": "admin", "ip": "192.168.1.157", "chip": "M1 Pro", "ram": 16},
}

# SSH key for remote connections
SSH_KEY = Path.home() / ".ssh" / "id_ed25519"

# ANSI colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"
BOLD = "\033[1m"


def print_header(msg: str):
    """Print a formatted header."""
    print(f"\n{BOLD}{BLUE}{'='*60}{RESET}")
    print(f"{BOLD}{BLUE}{msg}{RESET}")
    print(f"{BOLD}{BLUE}{'='*60}{RESET}\n")


def print_status(name: str, status: str, details: str = ""):
    """Print a status line."""
    if status == "ok":
        icon = f"{GREEN}✓{RESET}"
    elif status == "warn":
        icon = f"{YELLOW}⚠{RESET}"
    else:
        icon = f"{RED}✗{RESET}"
    
    extra = f" ({details})" if details else ""
    print(f"  {icon} {name}{extra}")


def run_ssh(node_name: str, command: str, timeout: int = 30) -> Tuple[bool, str]:
    """Run a command on a remote node via SSH."""
    node = NODES[node_name]
    
    if node_name == "brain":
        # Local execution
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result.returncode == 0, result.stdout + result.stderr
        except Exception as e:
            return False, str(e)
    
    # Remote SSH
    ssh_cmd = [
        "ssh",
        "-i", str(SSH_KEY),
        "-o", "ConnectTimeout=10",
        "-o", "StrictHostKeyChecking=no",
        "-o", "BatchMode=yes",
        f"{node['user']}@{node['host']}",
        command
    ]
    
    try:
        result = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result.returncode == 0, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return False, "SSH timeout"
    except Exception as e:
        return False, str(e)


def check_turboquant_local() -> bool:
    """Check if TurboQuant is installed locally on Brain."""
    if not TURBOQUANT_PATH.exists():
        return False
    
    # Check if it's importable
    try:
        sys.path.insert(0, str(TURBOQUANT_PATH))
        import turboquant_mlx
        return True
    except ImportError:
        return False


def check_grove_local() -> bool:
    """Check if Grove is installed locally on Brain."""
    if not GROVE_PATH.exists():
        return False
    
    try:
        sys.path.insert(0, str(GROVE_PATH))
        import grove
        return True
    except ImportError:
        return False


def check_node_status(node_name: str) -> Dict:
    """Check TurboQuant status on a node."""
    status = {
        "reachable": False,
        "python_ok": False,
        "mlx_ok": False,
        "turboquant_ok": False,
        "cache_dir_ok": False,
        "chip": NODES[node_name]["chip"],
        "ram": NODES[node_name]["ram"],
    }
    
    # Check reachability
    success, output = run_ssh(node_name, "echo ok", timeout=10)
    status["reachable"] = success
    
    if not success:
        return status
    
    # Check Python
    success, output = run_ssh(node_name, "python3 --version", timeout=10)
    status["python_ok"] = success and "Python 3" in output
    
    # Check MLX
    success, output = run_ssh(node_name, "python3 -c 'import mlx.core as mx; print(mx.__version__)'", timeout=15)
    status["mlx_ok"] = success
    
    # Check if turboquant is accessible (either installed or symlinked)
    check_cmd = "python3 -c 'import sys; sys.path.insert(0, \"/Users/ravenx/Projects/turboquant-mlx\" if __import__(\"os\").path.exists(\"/Users/ravenx/Projects/turboquant-mlx\") else \".\"); import turboquant_mlx; print(\"ok\")'"
    success, output = run_ssh(node_name, check_cmd, timeout=15)
    status["turboquant_ok"] = success and "ok" in output
    
    # Check cache directory
    success, output = run_ssh(node_name, "ls -la ~/.turboquant/kv-cache/ 2>/dev/null || echo 'not found'", timeout=10)
    status["cache_dir_ok"] = success and "not found" not in output
    
    return status


def setup_cache_dir(node_name: str) -> bool:
    """Create TurboQuant cache directory on a node."""
    success, _ = run_ssh(node_name, "mkdir -p ~/.turboquant/kv-cache", timeout=10)
    return success


def apply_exo_patch() -> bool:
    """Apply the TurboQuant exo patch on Brain."""
    patch_script = TURBOQUANT_PATH / "patch_exo.py"
    
    if not patch_script.exists():
        print(f"  {RED}✗{RESET} Patch script not found: {patch_script}")
        return False
    
    try:
        result = subprocess.run(
            ["python3", str(patch_script)],
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.returncode == 0:
            print(f"  {GREEN}✓{RESET} exo patch applied successfully")
            return True
        else:
            print(f"  {RED}✗{RESET} Patch failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"  {RED}✗{RESET} Patch error: {e}")
        return False


def sync_turboquant_to_node(node_name: str) -> bool:
    """Sync TurboQuant to a remote node via rsync."""
    if node_name == "brain":
        return True  # Already local
    
    node = NODES[node_name]
    dest = f"{node['user']}@{node['host']}:~/Projects/"
    
    # Create Projects dir first
    run_ssh(node_name, "mkdir -p ~/Projects", timeout=10)
    
    try:
        result = subprocess.run([
            "rsync", "-avz", "--delete",
            "-e", f"ssh -i {SSH_KEY} -o StrictHostKeyChecking=no",
            str(TURBOQUANT_PATH) + "/",
            f"{dest}turboquant-mlx/"
        ], capture_output=True, text=True, timeout=120)
        return result.returncode == 0
    except Exception as e:
        print(f"  {RED}✗{RESET} rsync failed: {e}")
        return False


def print_status_table(statuses: Dict[str, Dict]):
    """Print a formatted status table."""
    print(f"\n{BOLD}Node Status Table:{RESET}")
    print(f"{'─'*80}")
    print(f"{'Node':<10} {'Chip':<10} {'RAM':<6} {'Reach':<7} {'Python':<8} {'MLX':<6} {'TQ':<6} {'Cache':<6}")
    print(f"{'─'*80}")
    
    for node_name, status in statuses.items():
        def icon(ok): return f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"
        
        print(f"{node_name:<10} {status['chip']:<10} {status['ram']:<4}GB "
              f"{icon(status['reachable']):<7} {icon(status['python_ok']):<8} "
              f"{icon(status['mlx_ok']):<6} {icon(status['turboquant_ok']):<6} {icon(status['cache_dir_ok']):<6}")
    
    print(f"{'─'*80}")


def main():
    parser = argparse.ArgumentParser(description="Integrate TurboQuant + Grove on Star Platinum cluster")
    parser.add_argument("--check-only", action="store_true", help="Only check status, don't modify")
    parser.add_argument("--apply-patch", action="store_true", help="Apply exo patch")
    parser.add_argument("--sync", action="store_true", help="Sync TurboQuant to all nodes")
    args = parser.parse_args()
    
    print_header("Star Platinum TurboQuant + Grove Integration")
    
    # Step 1: Check local installations
    print(f"{BOLD}1. Checking local Brain installations...{RESET}")
    
    tq_ok = check_turboquant_local()
    print_status("TurboQuant-MLX", "ok" if tq_ok else "error", str(TURBOQUANT_PATH))
    
    grove_ok = check_grove_local()
    print_status("Grove-MLX", "ok" if grove_ok else "error", str(GROVE_PATH))
    
    if not tq_ok:
        print(f"\n{RED}ERROR: TurboQuant not found at {TURBOQUANT_PATH}{RESET}")
        print("Clone it with: git clone https://github.com/DeadByDawn101/turboquant-mlx ~/Projects/turboquant-mlx")
        sys.exit(1)
    
    # Step 2: Check all nodes
    print(f"\n{BOLD}2. Checking cluster node status...{RESET}")
    
    statuses = {}
    for node_name in NODES:
        print(f"  Checking {node_name}...", end=" ", flush=True)
        statuses[node_name] = check_node_status(node_name)
        status_icon = f"{GREEN}✓{RESET}" if statuses[node_name]["reachable"] else f"{RED}✗{RESET}"
        print(status_icon)
    
    print_status_table(statuses)
    
    if args.check_only:
        print(f"\n{YELLOW}Check-only mode, exiting.{RESET}")
        return
    
    # Step 3: Setup cache directories
    print(f"\n{BOLD}3. Setting up cache directories...{RESET}")
    
    for node_name in NODES:
        if statuses[node_name]["reachable"]:
            success = setup_cache_dir(node_name)
            print_status(f"{node_name} cache dir", "ok" if success else "error")
        else:
            print_status(f"{node_name} cache dir", "warn", "node unreachable")
    
    # Step 4: Sync TurboQuant to nodes (if requested)
    if args.sync:
        print(f"\n{BOLD}4. Syncing TurboQuant to worker nodes...{RESET}")
        
        for node_name in NODES:
            if node_name == "brain":
                continue
            
            if statuses[node_name]["reachable"]:
                print(f"  Syncing to {node_name}...", end=" ", flush=True)
                success = sync_turboquant_to_node(node_name)
                print(f"{GREEN}✓{RESET}" if success else f"{RED}✗{RESET}")
            else:
                print(f"  Skipping {node_name} (unreachable)")
    
    # Step 5: Apply exo patch (if requested)
    if args.apply_patch:
        print(f"\n{BOLD}5. Applying exo patch...{RESET}")
        apply_exo_patch()
    
    # Final status
    print(f"\n{BOLD}Integration Summary:{RESET}")
    print(f"{'─'*40}")
    
    reachable = sum(1 for s in statuses.values() if s["reachable"])
    tq_ready = sum(1 for s in statuses.values() if s["turboquant_ok"])
    cache_ready = sum(1 for s in statuses.values() if s["cache_dir_ok"])
    
    print(f"  Nodes reachable:      {reachable}/{len(NODES)}")
    print(f"  TurboQuant ready:     {tq_ready}/{len(NODES)}")
    print(f"  Cache dirs ready:     {cache_ready}/{len(NODES)}")
    
    print(f"\n{BOLD}Next steps:{RESET}")
    print("  1. Run autoresearch:  python3 scripts/run_autoresearch.py")
    print("  2. Apply exo patch:   python3 scripts/integrate_turboquant.py --apply-patch")
    print("  3. Sync to workers:   python3 scripts/integrate_turboquant.py --sync")
    
    # Save integration status
    status_file = CLUSTER_PATH / "research" / "integration_status.json"
    status_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(status_file, "w") as f:
        json.dump({
            "timestamp": __import__("time").time(),
            "nodes": {k: {kk: vv for kk, vv in v.items() if isinstance(vv, (bool, str, int, float))} 
                     for k, v in statuses.items()},
            "turboquant_path": str(TURBOQUANT_PATH),
            "grove_path": str(GROVE_PATH),
        }, f, indent=2)
    
    print(f"\n  Status saved to: {status_file}")


if __name__ == "__main__":
    main()
