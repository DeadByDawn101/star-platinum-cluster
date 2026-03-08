#!/usr/bin/env python3
"""STAR PLATINUM scheduler service.
Routes tasks to local core model, ANE worker, DirectReduce, or hosted fallback models.
"""

from __future__ import annotations

from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, List
import json
import os


@dataclass
class Task:
    task_type: str
    payload: Dict[str, Any]


class Scheduler:
    def __init__(self) -> None:
        self.core_model = os.getenv("SPC_CORE_MODEL", "ollama/qwen2.5:14b")
        self.fallbacks: List[str] = [
            "anthropic/claude-sonnet-4-6",
            "openai-codex/gpt-5.3-codex",
            "xai/grok-4",
            "google/gemini-2.0-flash",
            "minimax-portal/MiniMax-M2.5",
        ]

    def route(self, task: Task) -> Dict[str, Any]:
        if task.task_type in {"embedding_train", "tiny_finetune", "kernel_benchmark"}:
            return {"route": "ane_worker", "target": "http://127.0.0.1:9091/run", "reason": "ANE-eligible training/compute task"}

        if task.task_type in {"all_reduce", "gradient_sync", "state_sync"}:
            return {"route": "directreduce", "target": "http://127.0.0.1:9092/allreduce", "reason": "Collective sync offload path"}

        if task.task_type in {"long_context", "multi_tool_complex", "high_reasoning"}:
            return {"route": "hosted", "model": self.fallbacks[0], "reason": "High reasoning/context"}

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
            self._send(200, {"ok": True, "service": "scheduler", "core_model": scheduler.core_model, "fallback_count": len(scheduler.fallbacks)})
            return
        self._send(404, {"error": "not_found"})

    def do_POST(self):  # noqa: N802
        if self.path != "/route":
            self._send(404, {"error": "not_found"})
            return

        length = int(self.headers.get("Content-Length", "0"))
        data = self.rfile.read(length)
        req = json.loads(data or b"{}")
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
