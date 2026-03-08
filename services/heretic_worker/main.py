#!/usr/bin/env python3
"""Heretic local model worker (gpt-oss-20b-heretic).
Loads a local HF model directory and exposes /health + /run endpoints.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os

MODEL_DIR = os.getenv("SPC_HERETIC_MODEL_DIR", "/Users/ravenx/Models/hf/gpt-oss-20b-heretic")
MAX_NEW_TOKENS = int(os.getenv("SPC_HERETIC_MAX_NEW_TOKENS", "220"))

_model = None
_tokenizer = None
_load_error = None


def load_model_once() -> None:
    global _model, _tokenizer, _load_error
    if _model is not None or _load_error is not None:
        return
    try:
        from transformers import AutoTokenizer, AutoModelForCausalLM
        import torch

        _tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
        _model = AutoModelForCausalLM.from_pretrained(
            MODEL_DIR,
            torch_dtype=torch.bfloat16 if torch.backends.mps.is_available() else torch.float16,
            device_map="auto",
        )
    except Exception as e:  # pragma: no cover
        _load_error = str(e)


def infer(prompt: str) -> str:
    from transformers import TextStreamer
    import torch

    inputs = _tokenizer(prompt, return_tensors="pt")
    if torch.backends.mps.is_available():
        inputs = {k: v.to("mps") for k, v in inputs.items()}
    elif torch.cuda.is_available():
        inputs = {k: v.to("cuda") for k, v in inputs.items()}

    output = _model.generate(
        **inputs,
        max_new_tokens=MAX_NEW_TOKENS,
        do_sample=True,
        temperature=0.7,
        top_p=0.9,
    )
    text = _tokenizer.decode(output[0], skip_special_tokens=True)
    return text


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, payload: dict) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            load_model_once()
            if _load_error:
                self._send(200, {"ok": False, "service": "heretic_worker", "model_dir": MODEL_DIR, "error": _load_error})
                return
            self._send(200, {"ok": True, "service": "heretic_worker", "model_dir": MODEL_DIR, "loaded": _model is not None})
            return
        self._send(404, {"error": "not_found"})

    def do_POST(self):  # noqa: N802
        if self.path != "/run":
            self._send(404, {"error": "not_found"})
            return

        length = int(self.headers.get("Content-Length", "0"))
        data = self.rfile.read(length)
        req = json.loads(data or b"{}")
        prompt = req.get("prompt", "Say hello in one line.")

        load_model_once()
        if _load_error:
            self._send(500, {"ok": False, "error": _load_error})
            return

        try:
            result = infer(prompt)
        except Exception as e:
            self._send(500, {"ok": False, "error": str(e)})
            return

        self._send(200, {"ok": True, "model": "gpt-oss-20b-heretic", "text": result})


def main() -> None:
    host = os.getenv("SPC_HERETIC_HOST", "127.0.0.1")
    port = int(os.getenv("SPC_HERETIC_PORT", "9094"))
    server = HTTPServer((host, port), Handler)
    print(f"heretic_worker listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
