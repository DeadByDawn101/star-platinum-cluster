#!/usr/bin/env python3
"""STAR PLATINUM scheduler v0.
Routes tasks to local Qwen core, ANE worker, or hosted fallback models.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List
import json


@dataclass
class Task:
    task_type: str
    payload: Dict[str, Any]


class Scheduler:
    def __init__(self) -> None:
        self.core_model = "ollama/qwen2.5:14b"
        self.fallbacks: List[str] = [
            "anthropic/claude-sonnet-4-6",
            "openai-codex/gpt-5.3-codex",
            "xai/grok-4",
            "google/gemini-2.0-flash",
            "minimax-portal/MiniMax-M2.5",
        ]

    def route(self, task: Task) -> Dict[str, Any]:
        if task.task_type in {"embedding_train", "tiny_finetune", "kernel_benchmark"}:
            return {"route": "ane_worker", "reason": "ANE-eligible training/compute task"}

        if task.task_type in {"long_context", "multi_tool_complex", "high_reasoning"}:
            return {"route": "hosted", "model": self.fallbacks[0], "reason": "High reasoning/context"}

        return {"route": "local", "model": self.core_model, "reason": "Local-first default"}


if __name__ == "__main__":
    scheduler = Scheduler()
    sample = Task(task_type="routine", payload={"prompt": "health check"})
    print(json.dumps(scheduler.route(sample), indent=2))
