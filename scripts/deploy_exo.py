#!/usr/bin/env python3
"""
Star Platinum — Exo Pipeline Deployer
Forces Pipeline parallelism over TB4 TCP/IP for optimal cluster throughput.
Usage: exo-pipe [model_id]
"""

import requests
import argparse
import sys
import json

EXO_HOST = "http://localhost:52415"

def get_cluster_nodes():
    """Check what nodes exo sees."""
    try:
        r = requests.get(f"{EXO_HOST}/node_id", timeout=3)
        node_id = r.json()
        print(f"[*] Brain node: {node_id}")
    except Exception:
        pass

def deploy_pipeline(model_id, host=EXO_HOST, dry_run=False):
    print(f"\n🖤 Star Platinum — Deploying '{model_id}' via Pipeline")
    print(f"   Host: {host}")
    
    try:
        # Step 1: Fetch previews
        print(f"\n[*] Querying cluster for deployment topology...")
        response = requests.get(f"{host}/instance/previews?model_id={model_id}", timeout=10)
        response.raise_for_status()
        data = response.json()
        previews = data.get("previews", [])
        
        if not previews:
            print("[!] No previews returned — is the model ID correct?")
            sys.exit(1)
        
        print(f"[*] Available topologies:")
        for p in previews:
            err = p.get("error") or "✅ viable"
            mem = p.get("memory_delta_by_node")
            print(f"    {p.get('sharding'):10} / {p.get('instance_meta'):12} — {err}")
        
        # Step 2: Find best Pipeline + MlxRing topology (TB4 TCP/IP)
        pipeline_payload = None
        for p in previews:
            if p.get("sharding") == "Pipeline" and p.get("error") is None:
                if p.get("instance_meta") == "MlxRing":  # TCP/IP, not RDMA
                    pipeline_payload = p.get("instance")
                    print(f"\n[+] Selected: Pipeline / MlxRing (TB4 TCP/IP optimized)")
                    break
        
        # Fallback: any working Pipeline
        if not pipeline_payload:
            for p in previews:
                if p.get("sharding") == "Pipeline" and p.get("error") is None:
                    pipeline_payload = p.get("instance")
                    print(f"\n[+] Selected: Pipeline / {p.get('instance_meta')} (fallback)")
                    break
        
        if not pipeline_payload:
            print(f"\n[!] No viable Pipeline topology found for {model_id}")
            print("[!] Check: all nodes online? Enough total RAM?")
            print(f"    Run: curl '{host}/instance/previews?model_id={model_id}' | python3 -m json.tool")
            sys.exit(1)
        
        # Show placement
        if pipeline_payload and "node_placements" in pipeline_payload:
            print(f"\n[*] Node placements:")
            for np in pipeline_payload["node_placements"]:
                layers = np.get("layers", [])
                layer_range = f"layers {min(layers)}–{max(layers)}" if layers else "unknown"
                print(f"    {np.get('node_id', 'unknown')[:20]}... → {layer_range}")
        
        if dry_run:
            print(f"\n[DRY RUN] Would deploy: {json.dumps({'instance': pipeline_payload})[:200]}...")
            return
        
        # Step 3: Deploy
        print(f"\n[*] Deploying to cluster...")
        deploy_r = requests.post(f"{host}/instance", json={"instance": pipeline_payload}, timeout=15)
        deploy_r.raise_for_status()
        
        print(f"[+] ✅ Success! Pipeline deployment initiated.")
        print(f"[+] Model: {model_id}")
        print(f"[+] API: {host}/v1/chat/completions")
        print(f"\n    Test: curl {host}/v1/chat/completions \\")
        print(f"      -H 'Content-Type: application/json' \\")
        print(f"      -d '{{\"model\":\"{model_id}\",\"messages\":[{{\"role\":\"user\",\"content\":\"hello\"}}]}}'")
        
    except requests.exceptions.ConnectionError:
        print(f"[!] Cannot connect to Exo at {host}")
        print("[!] Start exo first: cd ~/Projects/star-platinum-cluster && bash scripts/exo_start.sh")
    except requests.exceptions.RequestException as e:
        print(f"[!] API error: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Force Exo Pipeline sharding over TB4")
    parser.add_argument("model", nargs="?", default="mlx-community/Qwen3.5-122B-A10B-4bit",
                        help="HuggingFace model ID (default: Qwen3.5-122B)")
    parser.add_argument("--host", default=EXO_HOST, help="Exo API host")
    parser.add_argument("--dry-run", action="store_true", help="Preview without deploying")
    args = parser.parse_args()
    
    deploy_pipeline(args.model, host=args.host, dry_run=args.dry_run)
