#!/usr/bin/env python3
"""STAR PLATINUM scheduler service.
Routes tasks to local core model, ANE worker, DirectReduce, cluster nodes, or hosted fallbacks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, List, Optional
import json
import os
import time
from pathlib import Path


@dataclass
class Task:
    task_type: str
    payload: Dict[str, Any]


@dataclass
class Node:
    node_id: str
    role: str
    host: str
    port: int
    capabilities: List[str] = field(default_factory=list)
    status: str = "online"
    updated_at: float = field(default_factory=lambda: time.time())
    last_health_check: float = field(default_factory=lambda: 0)

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def is_fresh(self, ttl_s: int = 120) -> bool:
        """Node is fresh if checked within TTL window."""
        return (time.time() - self.last_health_check) < ttl_s

class PersistentNodeRegistry:
    """Persistent node registry with heartbeat freshness tracking"""
    
    def __init__(self, node_ttl_s: int = 120):
        self.node_ttl_s = node_ttl_s
        self.data_path = Path(os.getenv("SPC_NODE_REGISTRY_PATH", "/tmp/spc_nodes.json"))
        self.nodes: Dict[str, Node] = {}
        self._load()
    
    def _load(self) -> None:
        """Load nodes from persistent storage"""
        if self.data_path.exists():
            try:
                data = json.loads(self.data_path.read_text())
                for node_id, node_data in data.get("nodes", {}).items():
                    self.nodes[node_id] = Node(
                        node_id=node_id,
                        role=node_data["role"],
                        host=node_data["host"],
                        port=node_data["port"],
                        capabilities=node_data["capabilities"],
                        status=node_data["status"],
                        updated_at=node_data["updated_at"],
                    )
            except Exception as e:
                print(f"Warning: Failed to load node registry: {e}")
    
    def _save(self) -> None:
        """Persist nodes to disk"""
        try:
            self.data_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "nodes": {
                    node_id: {
                        "node_id": n.node_id,
                        "role": n.role,
                        "host": n.host,
                        "port": n.port,
                        "capabilities": n.capabilities,
                        "status": n.status,
                        "updated_at": n.updated_at,
                    }
                    for node_id, n in self.nodes.items()
                },
                "last_update": time.time(),
            }
            self.data_path.write_text(json.dumps(data, indent=2))
        except Exception as e:
            print(f"Warning: Failed to persist node registry: {e}")
    
    def register_node(self, node: Node) -> Node:
        """Register a node and persist to disk"""
        self.nodes[node.node_id] = node
        self._save()
        return node
    
    def remove_node(self, node_id: str) -> bool:
        """Remove a node and persist to disk"""
        if node_id in self.nodes:
            del self.nodes[node_id]
            self._save()
            return True
        return False
    
    def update_node_health(self, node_id: str) -> None:
        """Update last health check timestamp for a node"""
        if node_id in self.nodes:
            self.nodes[node_id].last_health_check = time.time()
    
    def active_nodes(self) -> List[Node]:
        """Return only fresh, active nodes"""
        now = time.time()
        active: List[Node] = []
        for n in self.nodes.values():
            if n.status != "online":
                continue
            if (now - n.updated_at) > self.node_ttl_s:
                continue
            active.append(n)
        return active
    
    def node_with_capabilities(self, required_caps: Optional[List[str]] = None) -> Optional[Node]:
        """Find a fresh, active node with required capabilities"""
        required_caps = required_caps or []
        for n in self.active_nodes():
            if all(cap in n.capabilities for cap in required_caps):
                return n
        return None
    
    def health_check(self, node_id: str) -> bool:
        """Perform health check on node and update timestamp if successful"""
        try:
            import urllib.request
            node = self.nodes.get(node_id)
            if not node:
                return False
            url = f"{node.base_url}/health"
            request = urllib.request.Request(url, method="GET", headers={"User-Agent": "StarPlatinum/1.0"})
            with urllib.request.urlopen(request, timeout=5) as response:
                if response.status == 200:
                    node.last_health_check = time.time()
                    return True
        except Exception:
            pass
        return False
    
    def cluster_status(self) -> Dict[str, Any]:
        """Get cluster health status"""
        nodes = self.active_nodes()
        ane_nodes = [n for n in nodes if "ane" in n.capabilities]
        rdma_nodes = [n for n in nodes if "rdma" in n.capabilities]
        total_nodes = len(nodes)
        health_checks_passed = sum(1 for n in nodes if (time.time() - n.last_health_check) < 60)
        
        return {
            "total_active_nodes": total_nodes,
            "ane_nodes": len(ane_nodes),
            "rdma_nodes": len(rdma_nodes),
            "nodes_with_recent_health_checks": health_checks_passed,
            "registry_status": "healthy" if total_nodes > 0 else "empty",
            "data_path": str(self.data_path),
        }


class Scheduler:
    def __init__(self) -> None:
        self.core_model = os.getenv("SPC_CORE_MODEL", "ollama/qwen2.5:32b")
        self.fallbacks: List[str] = [
            "anthropic/claude-sonnet-4-6",
            "openai-codex/gpt-5.3-codex",
            "xai/grok-4",
            "google/gemini-2.0-flash",
            "minimax-portal/MiniMax-M2.5",
        ]
        self.registry = PersistentNodeRegistry()
        self.node_ttl_s = int(os.getenv("SPC_NODE_TTL_S", "120"))

    def register_node(self, payload: Dict[str, Any]) -> Node:
        node_id = payload["node_id"]
        node = Node(
            node_id=node_id,
            role=payload.get("role", "worker"),
            host=payload.get("host", "127.0.0.1"),
            port=int(payload.get("port", 9090)),
            capabilities=list(payload.get("capabilities", [])),
            status=payload.get("status", "online"),
            updated_at=time.time(),
        )
        self.registry.register_node(node)
        return node

    def _active_nodes(self) -> List[Node]:
        return self.registry.active_nodes()

    def _pick_node(self, required_caps: Optional[List[str]] = None) -> Optional[Node]:
        required_caps = required_caps or []
        return self.registry.node_with_capabilities(required_caps)

    def _node_route(self, node: Optional[Node], endpoint: str, reason: str) -> Optional[Dict[str, Any]]:
        if not node:
            return None
        return {
            "route": "cluster_node",
            "node_id": node.node_id,
            "node_role": node.role,
            "target": f"{node.base_url}{endpoint}",
            "reason": reason,
        }

    def route(self, task: Task) -> Dict[str, Any]:
        if task.task_type in {"embedding_train", "tiny_finetune", "kernel_benchmark"}:
            # Prefer a registered ANE-capable node, fallback local ane_worker.
            node_route = self._node_route(
                self._pick_node(["ane"]),
                "/run",
                "ANE-eligible task routed to registered ANE node",
            )
            if node_route:
                return node_route
            return {
                "route": "ane_worker",
                "target": "http://127.0.0.1:9091/run",
                "reason": "ANE-eligible training/compute task (local fallback)",
            }

        if task.task_type in {"all_reduce", "gradient_sync", "state_sync"}:
            # Prefer beast/rdma-capable node, fallback local directreduce.
            node_route = self._node_route(
                self._pick_node(["rdma"]),
                "/allreduce",
                "Collective sync offload routed to RDMA-capable node",
            )
            if node_route:
                return node_route
            return {
                "route": "directreduce",
                "target": "http://127.0.0.1:9092/allreduce",
                "reason": "Collective sync offload path (local fallback)",
            }

        if task.task_type in {"long_context", "multi_tool_complex", "high_reasoning"}:
            return {
                "route": "hosted",
                "model": self.fallbacks[0],
                "reason": "High reasoning/context",
            }

        return {"route": "local", "model": self.core_model, "reason": "Local-first default"}


scheduler = Scheduler()


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, payload: Dict[str, Any]) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            self._send(
                200,
                {
                    "ok": True,
                    "service": "scheduler",
                    "core_model": scheduler.core_model,
                    "fallback_count": len(scheduler.fallbacks),
                    "active_nodes": len(scheduler._active_nodes()),
                    "cluster": scheduler.registry.cluster_status(),
                },
            )
            return

        if self.path == "/cluster/status":
            self._send(200, {"ok": True, "cluster": scheduler.registry.cluster_status()})
            return

        if self.path == "/nodes":
            self._send(
                200,
                {
                    "ok": True,
                    "nodes": [
                        {
                            "node_id": n.node_id,
                            "role": n.role,
                            "host": n.host,
                            "port": n.port,
                            "capabilities": n.capabilities,
                            "status": n.status,
                            "updated_at": n.updated_at,
                        }
                        for n in scheduler._active_nodes()
                    ],
                },
            )
            return

        self._send(404, {"error": "not_found"})

    def do_POST(self):  # noqa: N802
        if self.path not in {"/route", "/nodes/register"}:
            self._send(404, {"error": "not_found"})
            return

        length = int(self.headers.get("Content-Length", "0"))
        data = self.rfile.read(length)
        req = json.loads(data or b"{}")

        if self.path == "/nodes/register":
            try:
                node = scheduler.register_node(req)
            except KeyError as e:
                self._send(400, {"ok": False, "error": f"missing field: {e.args[0]}"})
                return
            self._send(
                200,
                {
                    "ok": True,
                    "registered": {
                        "node_id": node.node_id,
                        "role": node.role,
                        "host": node.host,
                        "port": node.port,
                        "capabilities": node.capabilities,
                        "status": node.status,
                    },
                },
            )
            return

        task = Task(task_type=req.get("task_type", "routine"), payload=req.get("payload", {}))
        self._send(200, {"ok": True, "decision": scheduler.route(task)})


def main() -> None:
    host = os.getenv("SPC_SCHEDULER_HOST", "127.0.0.1")
    port = int(os.getenv("SPC_SCHEDULER_PORT", "9090"))
    server = HTTPServer((host, port), Handler)
    print(f"scheduler listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
