#!/usr/bin/env python3
# Three-way report local server + background regenerator.
# Serves ~/ibitlabs/notebooks/ at http://127.0.0.1:8091/ ; / aliases to /report.html.
# Re-runs build_report.py every REGEN_INTERVAL seconds in a background thread.
import os, signal, subprocess, sys, threading, time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT           = 8092
ROOT           = Path.home() / "ibitlabs" / "notebooks"
BUILDER        = ROOT / "build_report.py"
REGEN_INTERVAL = 300  # seconds


def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def regen_once():
    try:
        r = subprocess.run([sys.executable, str(BUILDER)],
                           cwd=str(ROOT), capture_output=True, text=True, timeout=120)
        if r.returncode == 0:
            tail = (r.stdout or "").strip().splitlines()[-1:] or ["(no stdout)"]
            log(f"regen ok — {tail[0]}")
        else:
            log(f"regen rc={r.returncode}: {(r.stderr or '').strip()[:300]}")
    except subprocess.TimeoutExpired:
        log("regen timed out after 120s")
    except Exception as e:
        log(f"regen FAILED: {e!r}")


def regen_loop():
    regen_once()  # build immediately on startup
    while True:
        time.sleep(REGEN_INTERVAL)
        regen_once()


class ReportHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        if path in ("", "/", "/index.html"):
            path = "/report.html"
        return super().translate_path(path)

    def log_message(self, fmt, *args):
        log("http " + (fmt % args))


def main():
    os.chdir(ROOT)
    threading.Thread(target=regen_loop, daemon=True).start()
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), ReportHandler)
    log(f"serving {ROOT} on http://127.0.0.1:{PORT}/  (regen every {REGEN_INTERVAL}s)")
    srv.serve_forever()


if __name__ == "__main__":
    main()
