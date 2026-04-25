"""Ollama compatibility bridge.

Translates between the workbench backend contract:

    request   POST { "prompt": str, "max_tokens": int? }
    response  { "text": str }

and the Ollama native ``/api/generate`` contract:

    request   POST { "model": str, "prompt": str, "stream": false,
                     "options": { "num_predict": int? } }
    response  { "response": str, ... }

This is the first durable provider-specific backend bridge. The shape
(workbench-side framing handler + a small ``to_provider_request`` /
``from_provider_response`` pair) is the template for future providers
(OpenAI, Claude, etc.).

Run:

    venv/bin/python -m bridges.ollama_bridge

Then point the workbench at it:

    export MODEL_BACKEND_URL=http://127.0.0.1:11436
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer


OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11435/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:14b")
BRIDGE_HOST = os.getenv("BRIDGE_HOST", "127.0.0.1")
BRIDGE_PORT = int(os.getenv("BRIDGE_PORT", "11436"))
BRIDGE_TIMEOUT_SECONDS = int(os.getenv("BRIDGE_TIMEOUT_SECONDS", "600"))


def to_provider_request(workbench_payload: dict) -> dict:
    """Translate a workbench request payload to an Ollama request body."""
    body: dict = {
        "model": OLLAMA_MODEL,
        "prompt": workbench_payload["prompt"],
        "stream": False,
    }
    options: dict = {}
    max_tokens = workbench_payload.get("max_tokens")
    if max_tokens is not None:
        options["num_predict"] = int(max_tokens)
    if options:
        body["options"] = options
    return body


def from_provider_response(provider_data: dict) -> dict:
    """Translate an Ollama response body to a workbench response payload."""
    text = provider_data.get("response", "")
    if not isinstance(text, str):
        text = str(text)
    return {"text": text}


def call_ollama(provider_body: dict) -> dict:
    data = json.dumps(provider_body).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=BRIDGE_TIMEOUT_SECONDS) as resp:
        return json.loads(resp.read().decode("utf-8"))


class BridgeHandler(BaseHTTPRequestHandler):
    server_version = "OllamaBridge/0.1"

    def do_POST(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        try:
            workbench_payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError as e:
            self._json_error(400, f"invalid json: {e}")
            return
        if not isinstance(workbench_payload, dict) or "prompt" not in workbench_payload:
            self._json_error(400, "missing required field 'prompt'")
            return
        try:
            provider_body = to_provider_request(workbench_payload)
            provider_data = call_ollama(provider_body)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:500]
            self._json_error(502, f"ollama http {e.code}: {detail}")
            return
        except urllib.error.URLError as e:
            self._json_error(502, f"ollama unreachable: {e}")
            return
        except Exception as e:  # noqa: BLE001 — surface as 500
            self._json_error(500, f"bridge error: {e}")
            return
        self._json_ok(from_provider_response(provider_data))

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/health", "/healthz"):
            self._json_ok({"status": "ok", "model": OLLAMA_MODEL, "ollama": OLLAMA_URL})
            return
        self._json_error(404, "not found")

    def _json_ok(self, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json_error(self, code: int, msg: str) -> None:
        body = json.dumps({"error": msg}).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:  # quieter, stderr-only
        sys.stderr.write("[ollama_bridge] " + (fmt % args) + "\n")


def main() -> None:
    sys.stderr.write(
        f"[ollama_bridge] listening on http://{BRIDGE_HOST}:{BRIDGE_PORT} "
        f"-> {OLLAMA_URL} (model={OLLAMA_MODEL})\n"
    )
    HTTPServer((BRIDGE_HOST, BRIDGE_PORT), BridgeHandler).serve_forever()


if __name__ == "__main__":
    main()
