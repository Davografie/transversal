#!/usr/bin/env python3
"""Tiny HTTP server that lists LoRA files from the ComfyUI models directory.

Runs on port 8191 alongside ComfyUI (8188) and Ollama (11434).
No external dependencies — uses only stdlib.
"""

import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

LORAS_DIR = Path("/app/ComfyUI/models/loras/flux")


def list_loras() -> list[dict]:
    """Walk loras/flux and return [{name, path}] for all .safetensors files."""
    if not LORAS_DIR.exists():
        return []
    results = []
    for dirpath, _, filenames in os.walk(LORAS_DIR):
        for f in sorted(filenames):
            if f.endswith(".safetensors"):
                rel = os.path.relpath(os.path.join(dirpath, f), LORAS_DIR)
                name = rel.replace(".safetensors", "")
                results.append({"name": name, "path": rel})
    return results


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/loras":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(list_loras()).encode())
        elif self.path == "/health":
            self.send_response(200)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # silence logs


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 8191), Handler)
    print("LoRA server listening on :8191")
    server.serve_forever()
