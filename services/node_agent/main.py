#!/usr/bin/env python3
"""Star Platinum node agent — runs on each worker node, registers with brain scheduler."""

from __future__ import annotations
import json, os, socket, subprocess, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

BRAIN_HOST = os.getenv("SPC_BRAIN_HOST", "192.168.1.151")
BRAIN_PORT = int(os.getenv("SPC_BRAIN_PORT", "9090"))
NODE_ID    = os.getenv("SPC_NODE_ID", socket.gethostname().split(".")[0])
NODE_ROLE  = os.getenv("SPC_NODE_ROLE", "ane-worker")
NODE_PORT  = int(os.getenv("SPC_NODE_PORT", "9091"))
CAPS       = os.getenv("SPC_CAPS", "ane").split(",")
HEARTBEAT_INTERVAL = int(os.getenv("SPC_HEARTBEAT_S", "30"))

try:
    NODE_HOST = socket.gethostbyname(socket.gethostname())
except Exception:
    NODE_HOST = "127.0.0.1"

def get_stats() -> dict:
    stats: dict = {}
    for key, cmd in [
        ("mem_bytes", ["sysctl", "-n", "hw.memsize"]),
        ("cpu",       ["sysctl", "-n", "machdep.cpu.brand_string"]),
        ("model",     ["sysctl", "-n", "hw.model"]),
    ]:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
            val = r.stdout.strip()
            stats[key] = int(val) if key == "mem_bytes" else val
        except Exception:
            pass
    if "mem_bytes" in stats:
        stats["mem_gb"] = round(stats["mem_bytes"] / 1024**3, 1)
    return stats

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, payload):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())
    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"ok": True, "node_id": NODE_ID, "role": NODE_ROLE, "capabilities": CAPS, "stats": get_stats()})
        elif self.path == "/run":
            self._send(200, {"ok": True, "node_id": NODE_ID, "status": "ready"})
        else:
            self._send(404, {"error": "not_found"})
    def do_POST(self):
        if self.path == "/run":
            length = int(self.headers.get("Content-Length", "0"))
            data = json.loads(self.rfile.read(length) or b"{}")
            self._send(200, {"ok": True, "node_id": NODE_ID, "accepted": True, "task": data})
        else:
            self._send(404, {"error": "not_found"})

def heartbeat_loop():
    while True:
        try:
            payload = json.dumps({"node_id": NODE_ID, "role": NODE_ROLE, "host": NODE_HOST,
                                   "port": NODE_PORT, "capabilities": CAPS, "status": "online"}).encode()
            req = urllib.request.Request(f"http://{BRAIN_HOST}:{BRAIN_PORT}/nodes/register",
                data=payload, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=5) as r:
                resp = json.loads(r.read())
                print(f"[heartbeat] registered: {resp.get('registered',{}).get('node_id')}", flush=True)
        except Exception as e:
            print(f"[heartbeat] failed: {e}", flush=True)
        time.sleep(HEARTBEAT_INTERVAL)

def main():
    print(f"Star Platinum node agent — {NODE_ID} ({NODE_ROLE})", flush=True)
    print(f"Caps: {CAPS} | Brain: {BRAIN_HOST}:{BRAIN_PORT} | Port: {NODE_PORT}", flush=True)
    threading.Thread(target=heartbeat_loop, daemon=True).start()
    HTTPServer(("0.0.0.0", NODE_PORT), Handler).serve_forever()

if __name__ == "__main__":
    main()
