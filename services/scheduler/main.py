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

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


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
        self.node_ttl_s = int(os.getenv("SPC_NODE_TTL_S", "120"))
        self.nodes: Dict[str, Node] = {}

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
        self.nodes[node_id] = node
        return node

    def _active_nodes(self) -> List[Node]:
        now = time.time()
        active: List[Node] = []
        for n in self.nodes.values():
            if n.status != "online":
                continue
            if (now - n.updated_at) > self.node_ttl_s:
                continue
            active.append(n)
        return active

    def _pick_node(self, required_caps: Optional[List[str]] = None) -> Optional[Node]:
        required_caps = required_caps or []
        active = self._active_nodes()
        for n in active:
            if all(cap in n.capabilities for cap in required_caps):
                return n
        return None

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
                },
            )
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
