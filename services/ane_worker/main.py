#!/usr/bin/env python3
"""ANE worker wrapper (v0).
This process fronts ANE experiments so cluster can call a stable API.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import json


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, payload: dict) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            self._send(200, {"ok": True, "service": "ane_worker", "mode": "research"})
            return
        self._send(404, {"error": "not_found"})

    def do_POST(self):  # noqa: N802
        if self.path == "/run":
            # v0 placeholder for ANE graph compile/eval invocation
            self._send(200, {
                "accepted": True,
                "engine": "ANE",
                "note": "wire to DeadByDawn101/ANE compile+eval scripts",
            })
            return
        self._send(404, {"error": "not_found"})


def main() -> None:
    server = HTTPServer(("127.0.0.1", 9091), Handler)
    print("ane_worker listening on http://127.0.0.1:9091")
    server.serve_forever()


if __name__ == "__main__":
    main()
