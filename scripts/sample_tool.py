#!/usr/bin/env python3
"""
R5a Sample Intake Tool - lightweight operator helper for chapter smoke-test samples.

Modes:
  Server (default):
    python scripts/sample_tool.py
    Starts local HTTP server on port 8765, auto-opens browser with upload/paste form.

  CLI from file:
    python scripts/sample_tool.py --file <path> --name <name>

  CLI from stdin:
    pbpaste | python scripts/sample_tool.py --stdin --name <name>

All saved samples go to data/samples/ (gitignored). No pipeline code is touched.
"""

import json
import os
import re
import subprocess
import sys
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from threading import Thread

# --- Config ---
SAMPLES_DIR = Path("data/samples")
DEFAULT_BOOK_MEMORY = "data/book_memory/book_memory.json"
SMOKE_CMD_TEMPLATE = (
    "venv/bin/python -m app.cli chapter run --smoke-test"
    " --book-memory {book_memory} --source {source}"
)
DEFAULT_PORT = 8765
MAX_CONTENT_BYTES = 1024 * 1024  # 1 MB


# --- Validation ---

def validate_name(name: str) -> str | None:
    """Return an error message if name is invalid, else None."""
    if not name or not name.strip():
        return "Sample name is required."
    name = name.strip()
    if not re.match(r"^[a-zA-Z0-9_-]+$", name):
        return "Name may only contain letters, digits, hyphens, and underscores."
    if len(name) > 120:
        return "Name is too long (maximum 120 characters)."
    if name.startswith("-") or name.endswith("-"):
        return "Name may not start or end with a hyphen."
    return None


def validate_content(content: str) -> str | None:
    """Return an error message if content cannot be accepted, else None."""
    if not content or not content.strip():
        return "Sample content is empty."
    if "\0" in content:
        return "Sample appears to be binary (contains null bytes)."
    size = len(content.encode("utf-8"))
    if size > MAX_CONTENT_BYTES:
        return f"Sample too large ({size:,} bytes, limit {MAX_CONTENT_BYTES:,})."
    return None


def resolve_sample_path(name: str) -> Path:
    """Return the filesystem path for a validated sample name."""
    return (SAMPLES_DIR / name.strip()).with_suffix(".txt")


# --- Save ---

def save_sample(content: str, name: str, force: bool = False) -> dict:
    """
    Write *content* to ``data/samples/<name>.txt``.

    Returns a dict with at minimum ``ok`` (bool). On success also includes
    ``path``, ``bytes``, ``name``, and ``smoke_cmd``. On failure includes
    ``error`` and optionally ``path`` (if the file already existed).
    """
    err = validate_name(name)
    if err:
        return {"ok": False, "error": err}

    err = validate_content(content)
    if err:
        return {"ok": False, "error": err}

    name = name.strip()
    dest = resolve_sample_path(name)

    if dest.exists() and not force:
        return {
            "ok": False,
            "error": f"Already exists: {dest}",
            "path": str(dest),
        }

    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    old_size = dest.stat().st_size if dest.exists() else None
    dest.write_text(content, encoding="utf-8")
    new_size = dest.stat().st_size

    result = {
        "ok": True,
        "path": str(dest),
        "bytes": new_size,
        "name": name,
        "smoke_cmd": SMOKE_CMD_TEMPLATE.format(
            book_memory=DEFAULT_BOOK_MEMORY,
            source=str(dest),
        ),
    }
    if old_size is not None:
        result["overwritten"] = True
        result["old_bytes"] = old_size
    return result


def format_report(result: dict) -> str:
    """Format a save result dict into a human-readable terminal string."""
    if not result["ok"]:
        msg = f"ERROR: {result['error']}"
        if "path" in result:
            msg += f"\n       Path: {result['path']}"
        return msg

    lines = [
        f"Saved: {result['path']} ({result['bytes']:,} bytes)",
        "",
        "  Smoke-test command:",
        f"    {result['smoke_cmd']}",
    ]
    if result.get("overwritten"):
        old = result.get("old_bytes", "?")
        lines.insert(1, f"  (overwritten; was {old:,} bytes)")
    return "\n".join(lines)


# --- Smoke-test runner ---

def run_smoke_test(sample_path: str, timeout: int = 120) -> dict:
    """Shell out to the chapter smoke-test CLI and return the result."""
    cmd = SMOKE_CMD_TEMPLATE.format(
        book_memory=DEFAULT_BOOK_MEMORY,
        source=sample_path,
    )
    try:
        proc = subprocess.run(
            cmd.split(),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "ok": proc.returncode == 0,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "returncode": proc.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "stdout": "",
            "stderr": f"Subprocess timed out after {timeout}s",
            "returncode": -1,
        }
    except FileNotFoundError:
        return {
            "ok": False,
            "stdout": "",
            "stderr": "venv/bin/python not found",
            "returncode": -1,
        }
    except OSError as exc:
        return {
            "ok": False,
            "stdout": "",
            "stderr": f"OS error: {exc}",
            "returncode": -1,
        }


# --- HTTP Server ---

_SAMPLES_DIR_FOR_HANDLER = SAMPLES_DIR  # closure capture for the handler class


class SampleHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler for the sample intake web form."""

    # Quiet default request logging — only log POST saves.
    def log_request(self, code="-", size="-"):
        if self.command == "POST" and self.path in ("/save", "/run-smoke"):
            super().log_request(code, size)

    def _json(self, status: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict | None:
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > MAX_CONTENT_BYTES + 4096:
                self._json(413, {"ok": False, "error": "Payload too large"})
                return None
            raw = self.rfile.read(length)
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError, OSError):
            self._json(400, {"ok": False, "error": "Invalid JSON payload"})
            return None

    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
        else:
            self._json(404, {"ok": False, "error": "Not found"})

    def do_POST(self):
        if self.path == "/save":
            self._handle_save()
        elif self.path == "/run-smoke":
            self._handle_run_smoke()
        else:
            self._json(404, {"ok": False, "error": "Not found"})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _handle_save(self):
        payload = self._read_json_body()
        if payload is None:
            return
        name = payload.get("name", "")
        content = payload.get("content", "")
        force = payload.get("force", False)
        result = save_sample(content, name, force=force)
        status = 200 if result["ok"] else (409 if "exists" in result.get("error", "") else 400)
        self._json(status, result)

    def _handle_run_smoke(self):
        payload = self._read_json_body()
        if payload is None:
            return
        path = payload.get("path", "")
        if not path or not Path(path).exists():
            self._json(400, {"ok": False, "error": "Sample file not found on server"})
            return
        result = run_smoke_test(path)
        self._json(200, result)


def _find_port(start: int) -> int:
    """Return the first available port starting from *start*."""
    port = start
    while port < start + 100:
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                port += 1
    raise RuntimeError(f"No available port found in range {start}-{start + 99}")


def serve(port: int = DEFAULT_PORT, no_browser: bool = False):
    """Start the HTTP server and open a browser tab."""
    port = _find_port(port)
    server = HTTPServer(("127.0.0.1", port), SampleHandler)
    url = f"http://127.0.0.1:{port}"

    if not no_browser:

        def _open():
            import webbrowser
            webbrowser.open(url)

        Thread(target=_open, daemon=True).start()

    print(f"Sample Intake Tool — {url}")
    print("Press Ctrl+C to stop.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.server_close()


# --- HTML page (embedded) ---

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sample Intake Tool</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif; max-width: 640px; margin: 2em auto; padding: 0 1em; color: #1a1a1a; line-height: 1.5; }
  h1 { font-size: 1.3em; margin-bottom: 0.25em; }
  .sub { color: #555; font-size: 0.9em; margin-top: 0; }
  label { display: block; margin: 1em 0 0.25em; font-weight: 600; font-size: 0.9em; }
  input[type=text] { width: 100%; padding: 0.55em; border: 1px solid #bbb; border-radius: 4px; font-size: 0.95em; }
  input[type=text]:focus { border-color: #0066cc; outline: none; box-shadow: 0 0 0 2px rgba(0,102,204,0.15); }
  input[type=file] { font-size: 0.9em; }
  textarea { width: 100%; min-height: 130px; padding: 0.55em; border: 1px solid #bbb; border-radius: 4px; font-family: 'SF Mono', Monaco, 'Cascadia Code', Consolas, monospace; font-size: 0.85em; resize: vertical; }
  textarea:focus { border-color: #0066cc; outline: none; box-shadow: 0 0 0 2px rgba(0,102,204,0.15); }
  .divider { text-align: center; color: #999; margin: 0.6em 0; font-size: 0.85em; }
  .btn-row { margin-top: 1em; display: flex; gap: 0.5em; flex-wrap: wrap; align-items: center; }
  button { padding: 0.5em 1.2em; border: 1px solid #888; border-radius: 4px; background: #f5f5f5; cursor: pointer; font-size: 0.9em; }
  button:hover { background: #e8e8e8; }
  button.primary { background: #0066cc; color: #fff; border-color: #0055aa; }
  button.primary:hover { background: #0055aa; }
  button.danger { background: #c00; color: #fff; border-color: #a00; }
  button.danger:hover { background: #a00; }
  button:disabled { opacity: 0.5; cursor: default; }
  #result { margin-top: 1.5em; }
  .msg-error { color: #a00; background: #fff5f5; padding: 0.75em; border-radius: 4px; border: 1px solid #fcc; }
  .msg-success { color: #060; background: #f5fff5; padding: 0.75em; border-radius: 4px; border: 1px solid #cfc; }
  .cmd-box { background: #f5f5f5; padding: 0.75em; border-radius: 4px; font-family: 'SF Mono', Monaco, 'Cascadia Code', Consolas, monospace; font-size: 0.82em; word-break: break-all; margin: 0.5em 0; }
  pre.out { background: #fafafa; border: 1px solid #ddd; border-radius: 4px; padding: 0.5em; font-size: 0.82em; max-height: 300px; overflow: auto; white-space: pre-wrap; }
  .spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid #ccc; border-top-color: #0066cc; border-radius: 50%; animation: spin 0.6s linear infinite; vertical-align: middle; margin-right: 0.3em; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .file-hint { font-size: 0.82em; color: #888; margin-top: 0.15em; }
</style>
</head>
<body>
<h1>Chapter Sample Intake</h1>
<p class="sub">Save a chapter sample into <code>data/samples/</code> and get a ready-to-use smoke-test command.</p>

<form id="form">
  <label for="name">Sample name</label>
  <input type="text" id="name" autofocus required placeholder="e.g. ch_asclepius_01">

  <label for="file">Choose a file</label>
  <input type="file" id="file" accept=".txt,.text,text/plain,.md">
  <div class="file-hint" id="fileHint">Supported: .txt .md (plain text only)</div>

  <div class="divider">— or paste text —</div>

  <textarea id="paste" placeholder="Paste chapter text here..."></textarea>

  <div class="btn-row">
    <button type="submit" class="primary" id="saveBtn">Save Sample</button>
    <button type="button" id="clearBtn">Clear</button>
  </div>
</form>

<div id="result"></div>

<script>
(function() {
  var form = document.getElementById('form');
  var nameInput = document.getElementById('name');
  var fileInput = document.getElementById('file');
  var pasteArea = document.getElementById('paste');
  var saveBtn = document.getElementById('saveBtn');
  var clearBtn = document.getElementById('clearBtn');
  var resultDiv = document.getElementById('result');
  var fileHint = document.getElementById('fileHint');

  function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

  function busy(yes) {
    saveBtn.disabled = yes;
    saveBtn.textContent = yes ? 'Saving…' : 'Save Sample';
  }

  function render(data) {
    var h = '';
    if (data.ok) {
      h += '<div class="msg-success"><strong>✓ Saved:</strong> ' + esc(data.path) + ' (' + Number(data.bytes).toLocaleString() + ' bytes)';
      if (data.overwritten) h += '<br><em>(overwritten)</em>';
      h += '</div>';
      h += '<p><strong>Smoke-test command:</strong></p>';
      h += '<div class="cmd-box"><code>' + esc(data.smoke_cmd) + '</code></div>';
      h += '<div class="btn-row">';
      h += '  <button class="primary" id="runBtn">Run Smoke Test</button>';
      h += '  <button id="addAnotherBtn">Add Another</button>';
      h += '</div>';
      h += '<div id="smokeOut"></div>';
    } else {
      h += '<div class="msg-error"><strong>✗</strong> ' + esc(data.error);
      if (data.path) h += '<br>Path: ' + esc(data.path);
      h += '</div>';
    }
    resultDiv.innerHTML = h;

    var runBtn = document.getElementById('runBtn');
    if (runBtn) runBtn.addEventListener('click', function() { runSmoke(data.path); });
    var anotherBtn = document.getElementById('addAnotherBtn');
    if (anotherBtn) anotherBtn.addEventListener('click', resetForm);
  }

  function resetForm() {
    nameInput.value = '';
    fileInput.value = '';
    pasteArea.value = '';
    resultDiv.innerHTML = '';
    fileHint.textContent = 'Supported: .txt .md (plain text only)';
    nameInput.focus();
  }

  function runSmoke(path) {
    var outDiv = document.getElementById('smokeOut');
    if (!outDiv) return;
    var btn = document.getElementById('runBtn');
    if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Running…'; }

    outDiv.innerHTML = '<pre class="out">Starting smoke test…</pre>';

    fetch('/run-smoke', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: path })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var status = data.ok ? 'PASSED' : 'FAILED (exit ' + data.returncode + ')';
      var cls = data.ok ? 'msg-success' : 'msg-error';
      var out = '';
      if (data.stdout) out += '<pre class="out">' + esc(data.stdout) + '</pre>';
      if (data.stderr) out += '<pre class="out" style="color:#c00;">' + esc(data.stderr) + '</pre>';
      outDiv.innerHTML = '<div class="' + cls + '"><strong>Smoke test ' + status + '</strong></div>' + out;
      if (btn) { btn.disabled = false; btn.innerHTML = 'Run Smoke Test'; }
    })
    .catch(function(err) {
      outDiv.innerHTML = '<div class="msg-error"><strong>Error:</strong> ' + esc(err.message) + '</div>';
      if (btn) { btn.disabled = false; btn.innerHTML = 'Run Smoke Test'; }
    });
  }

  form.addEventListener('submit', function(e) {
    e.preventDefault();
    var name = nameInput.value.trim();
    if (!name) { render({ok:false, error:'Sample name is required.'}); return; }
    var file = fileInput.files && fileInput.files[0];
    var paste = pasteArea.value;

    if (!file && !paste.trim()) {
      render({ok:false, error:'Choose a file or paste text.'});
      return;
    }

    function save(content) {
      busy(true);
      fetch('/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name, content: content })
      })
      .then(function(r) { return r.json(); })
      .then(function(data) { render(data); busy(false); })
      .catch(function(err) { render({ok:false, error:'Network error: ' + err.message}); busy(false); });
    }

    if (file) {
      var reader = new FileReader();
      reader.onload = function(ev) { save(ev.target.result); };
      reader.onerror = function() { render({ok:false, error:'Failed to read file.'}); };
      reader.readAsText(file);
    } else {
      save(paste);
    }
  });

  clearBtn.addEventListener('click', resetForm);

  fileInput.addEventListener('change', function() {
    fileHint.textContent = this.files.length > 0
      ? 'File selected: ' + this.files[0].name
      : 'Supported: .txt .md (plain text only)';
  });
})();
</script>
</body>
</html>"""


# --- CLI mode ---

def cli_save(file_path: str | None, stdin: bool, name: str, force: bool):
    """CLI (non-server) save: read content from file or stdin and save."""
    if file_path:
        src = Path(file_path)
        if not src.exists():
            print(f"ERROR: file not found: {src}", file=sys.stderr)
            sys.exit(1)
        if src.stat().st_size == 0:
            print(f"ERROR: file is empty: {src}", file=sys.stderr)
            sys.exit(1)
        try:
            content = src.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            print(f"ERROR: cannot read file: {exc}", file=sys.stderr)
            sys.exit(1)
    elif stdin:
        content = sys.stdin.read()
        if not content.strip():
            print("ERROR: no input received via stdin (empty).", file=sys.stderr)
            sys.exit(1)
    else:
        print("ERROR: use --file <path> or --stdin to provide content.", file=sys.stderr)
        sys.exit(1)

    result = save_sample(content, name, force=force)
    print(format_report(result))
    if not result["ok"]:
        sys.exit(1)


# --- Entry point ---

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="R5a Sample Intake Tool — save chapter samples for smoke-test validation.",
    )
    parser.add_argument("--file", help="path to a plain-text chapter file")
    parser.add_argument("--stdin", action="store_true", help="read sample from stdin")
    parser.add_argument("--name", help="sample name (letters, digits, hyphens, underscores)")
    parser.add_argument("--force", action="store_true", help="overwrite existing sample")
    parser.add_argument("--no-browser", action="store_true", help="do not auto-open browser")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"server port (default: {DEFAULT_PORT})")

    args = parser.parse_args()

    if args.file or args.stdin:
        if not args.name:
            parser.error("--name is required with --file or --stdin")
        cli_save(file_path=args.file, stdin=args.stdin, name=args.name, force=args.force)
    else:
        if args.name:
            parser.error("--name is only valid with --file or --stdin")
        SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
        serve(port=args.port, no_browser=args.no_browser)


if __name__ == "__main__":
    main()
