#!/usr/bin/env python3
"""
moltbook_worker.py — Local HTTP worker on the Mac host that brokers all
Moltbook API calls. Sandbox (Cowork Linux) reaches it via
http://host.docker.internal:8765 with a bearer token.

Why this exists: the Moltbook API key is in macOS Keychain (host-only).
The sandbox can't read Keychain. Mounting the .env into the sandbox
would require a persistent Cowork directory mount. This worker avoids
both routes by keeping the key strictly in host-process memory and
only exposing thin, audited endpoints.

Endpoints (all require `Authorization: Bearer <token>` except /healthz):
  POST /moltbook/post-and-verify     — publish + auto-math verify
  POST /moltbook/comment-and-verify  — comment on a post + verify
  GET  /moltbook/home                — passthrough GET /api/v1/home
  GET  /moltbook/profile?name=...    — passthrough GET /api/v1/agents/profile
  GET  /moltbook/posts/:id           — passthrough GET /api/v1/posts/:id
  GET  /healthz                      — no auth; returns {"status":"ok"}

Bearer token location:
  - Generated at first startup (secrets.token_urlsafe(32))
  - Saved to ~/Library/Application Support/ibitlabs/moltbook-worker.token (0600)
  - Printed once to stdout on first startup
  - Reused on every subsequent startup from the token file
  - Retrieve any time: cat ~/Library/Application\\ Support/ibitlabs/moltbook-worker.token

Moltbook API key:
  - Loaded from macOS Keychain at startup (service=ibitlabs-moltbook-agent, account=ibitlabs)
  - Falls back to MOLTBOOK_API_KEY env var if Keychain missing
  - Never written to disk by this worker, never echoed to any response

Binding:
  - 127.0.0.1:8765 by default (localhost only; not exposed to network)
  - Override with --host / --port

Start via launchd (see com.ibitlabs.moltbook-worker.plist) or manually:
  python3 ~/ibitlabs/scripts/moltbook_worker.py
"""

from __future__ import annotations
import argparse
import json
import logging
import os
import secrets
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

# ─── Config ──────────────────────────────────────────────────────────
MOLTBOOK_BASE = "https://moltbook.com/api/v1"
TOKEN_DIR = Path.home() / "Library" / "Application Support" / "ibitlabs"
TOKEN_PATH = TOKEN_DIR / "moltbook-worker.token"
LOG_DIR = Path.home() / "ibitlabs" / "logs"
LOG_PATH = LOG_DIR / "moltbook-worker.log"

# ─── Logging ─────────────────────────────────────────────────────────
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("moltbook_worker")

# ─── Auth bootstrap ──────────────────────────────────────────────────
def ensure_token() -> str:
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    if TOKEN_PATH.exists():
        tok = TOKEN_PATH.read_text().strip()
        if tok:
            return tok
    tok = secrets.token_urlsafe(32)
    TOKEN_PATH.write_text(tok)
    os.chmod(TOKEN_PATH, 0o600)
    log.info("generated new worker token; saved to %s", TOKEN_PATH)
    print("\n" + "=" * 70)
    print("FIRST-RUN TOKEN (copy into sandbox env as MOLTBOOK_WORKER_TOKEN):")
    print(tok)
    print("=" * 70 + "\n", flush=True)
    return tok


def load_moltbook_key() -> str:
    # Try Keychain first
    try:
        r = subprocess.run(
            ["security", "find-generic-password",
             "-s", "ibitlabs-moltbook-agent",
             "-a", "ibitlabs", "-w"],
            check=True, capture_output=True, text=True, timeout=5,
        )
        key = r.stdout.strip()
        if key:
            log.info("moltbook key loaded from Keychain")
            return key
    except Exception as e:
        log.warning("keychain lookup failed: %s", e)
    # Env fallback
    key = os.environ.get("MOLTBOOK_API_KEY", "")
    if key:
        log.info("moltbook key loaded from MOLTBOOK_API_KEY env")
        return key
    log.error("no Moltbook API key available")
    sys.exit(2)

# ─── Math parser (reuse from moltbook_publish.py via import) ─────────
# Keep this file standalone-ish; duplicate the minimal math parser here.
# If moltbook_publish.py is on PYTHONPATH, prefer its newer version.
try:
    sys.path.insert(0, str(Path(__file__).parent))
    from moltbook_publish import compute_answer as _compute_answer  # type: ignore
    log.info("using compute_answer from moltbook_publish.py")
except Exception as e:
    log.warning("falling back to inline math parser: %s", e)
    import re as _re
    _NW = {"zero":0,"one":1,"two":2,"three":3,"four":4,"five":5,"six":6,"seven":7,
        "eight":8,"nine":9,"ten":10,"eleven":11,"twelve":12,"thirteen":13,
        "fourteen":14,"fifteen":15,"sixteen":16,"seventeen":17,"eighteen":18,
        "nineteen":19,"twenty":20,"thirty":30,"forty":40,"fifty":50,"sixty":60,
        "seventy":70,"eighty":80,"ninety":90,"hundred":100}
    _ADD = {"add","adds","plus","increases","increased","rises","rose","grows",
        "grew","speeds","accelerates","gains","and"}
    _SUB = {"reduces","reduced","decreases","decreased","shrinks","shrunk","falls",
        "fell","slows","slowed","loses","lost","minus","subtracts","decelerates",
        "diminishes","drops","dropped"}
    def _compute_answer(ch: str) -> float:
        letters = _re.sub(r"[^a-z]", "", ch.lower())
        # greedy tokenize
        toks = []
        i = 0
        vocab = list(_NW.keys()) + list(_ADD) + list(_SUB)
        vocab.sort(key=lambda x: -len(x))
        while i < len(letters):
            m = next((w for w in vocab if letters[i:i+len(w)] == w), None)
            if m:
                toks.append(m); i += len(m)
            else:
                i += 1
        op = "-" if any(t in _SUB for t in toks) else "+"
        groups: list[int] = []
        cur = 0
        seen_num = False
        for t in toks:
            if t in _NW:
                n = _NW[t]
                if n == 100:
                    cur = max(cur, 1) * 100
                else:
                    cur += n
                seen_num = True
            elif t in _ADD or t in _SUB:
                if seen_num:
                    groups.append(cur); cur = 0; seen_num = False
        if seen_num:
            groups.append(cur)
        if len(groups) >= 2:
            return groups[0] + groups[1] if op == "+" else groups[0] - groups[1]
        return float(sum(groups))

# ─── Moltbook HTTP helpers ───────────────────────────────────────────
def _mb(method: str, path: str, key: str, body: dict | None = None, timeout: int = 20) -> tuple[int, dict | None, str]:
    url = f"{MOLTBOOK_BASE}{path}"
    req = Request(url, method=method)
    req.add_header("Authorization", f"Bearer {key}")
    if body is not None:
        req.add_header("Content-Type", "application/json")
        data = json.dumps(body).encode("utf-8")
    else:
        data = None
    try:
        with urlopen(req, data=data, timeout=timeout) as r:
            raw = r.read().decode("utf-8", errors="replace")
            return r.status, json.loads(raw), raw
    except HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(raw), raw
        except Exception:
            return e.code, None, raw
    except Exception as e:
        return 0, None, str(e)

def mb_post_and_verify(key: str, title: str, body_text: str, submolt: str) -> dict:
    # 1) Create post
    status, j, raw = _mb("POST", "/posts", key,
        {"title": title, "content": body_text, "submolt_name": submolt})
    if status == 429:
        wait = 60
        if j and "retry_after_seconds" in j:
            wait = int(j["retry_after_seconds"]) + 5
        return {"ok": False, "error": "rate_limited", "retry_after_seconds": wait, "raw": raw[:400]}
    if status != 201 or not j:
        return {"ok": False, "error": f"post_http_{status}", "raw": raw[:400]}
    post = j.get("post") or {}
    pid = post.get("id")
    ver = post.get("verification") or {}
    code = ver.get("verification_code")
    challenge = ver.get("challenge_text", "")
    if not pid or not code:
        return {"ok": False, "error": "missing_verification_block", "raw": raw[:400]}
    # 2) Compute
    try:
        answer = _compute_answer(challenge)
    except Exception as e:
        return {"ok": False, "error": f"parse_challenge_failed: {e}",
                "post_id": pid, "challenge": challenge}
    ans_str = f"{float(answer):.2f}"
    # 3) Verify (one-shot; Moltbook marks failed permanently on wrong answer)
    vstatus, vj, vraw = _mb("POST", "/verify", key,
        {"verification_code": code, "answer": ans_str})
    if vstatus == 200 and vj and vj.get("success"):
        return {"ok": True, "post_id": pid, "url": f"https://moltbook.com/post/{pid}",
                "answer": ans_str, "challenge": challenge}
    # Verify failed: delete (it's marked failed, cleaner to remove)
    _mb("DELETE", f"/posts/{pid}", key)
    return {"ok": False, "error": f"verify_http_{vstatus}", "post_id": pid,
            "challenge": challenge, "computed_answer": ans_str, "raw": vraw[:400]}

def mb_comment_and_verify(key: str, post_id: str, content: str) -> dict:
    status, j, raw = _mb("POST", f"/posts/{post_id}/comments", key,
        {"content": content})
    if status == 429:
        wait = 60
        if j and "retry_after_seconds" in j:
            wait = int(j["retry_after_seconds"]) + 5
        return {"ok": False, "error": "rate_limited", "retry_after_seconds": wait}
    if status != 201 or not j:
        return {"ok": False, "error": f"comment_http_{status}", "raw": raw[:400]}
    c = j.get("comment") or {}
    cid = c.get("id")
    ver = c.get("verification") or {}
    code = ver.get("verification_code")
    challenge = ver.get("challenge_text", "")
    if not code:
        # Some comments may auto-publish without verify (legacy)
        return {"ok": True, "comment_id": cid, "no_verify_required": True}
    ans_str = f"{float(_compute_answer(challenge)):.2f}"
    vstatus, vj, _ = _mb("POST", "/verify", key,
        {"verification_code": code, "answer": ans_str})
    if vstatus == 200 and vj and vj.get("success"):
        return {"ok": True, "comment_id": cid, "answer": ans_str}
    return {"ok": False, "error": f"verify_http_{vstatus}", "comment_id": cid,
            "challenge": challenge, "computed_answer": ans_str}

# ─── HTTP handler ────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    server_version = "moltbook-worker/0.1"
    # These are populated on server construction
    moltbook_key: str = ""
    worker_token: str = ""

    def log_message(self, fmt, *args):  # route BaseHTTPRequestHandler log through our logger
        log.info("%s - %s", self.client_address[0], fmt % args)

    def _json(self, status: int, payload: dict):
        b = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(b)

    def _authed(self) -> bool:
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return False
        token = header[len("Bearer "):].strip()
        return secrets.compare_digest(token, self.worker_token)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def do_GET(self):
        u = urlparse(self.path)
        path = u.path
        qs = parse_qs(u.query)

        if path == "/healthz":
            return self._json(200, {"status": "ok", "service": "moltbook-worker", "ts": int(time.time())})

        if not self._authed():
            return self._json(401, {"error": "unauthorized"})

        if path == "/moltbook/home":
            status, j, raw = _mb("GET", "/home", self.moltbook_key)
            return self._json(status if status else 502, j if j else {"raw": raw[:400]})

        if path == "/moltbook/profile":
            name = (qs.get("name") or [""])[0]
            if not name:
                return self._json(400, {"error": "name_required"})
            status, j, raw = _mb("GET", f"/agents/profile?name={name}", self.moltbook_key)
            return self._json(status if status else 502, j if j else {"raw": raw[:400]})

        if path.startswith("/moltbook/posts/"):
            pid = path.split("/moltbook/posts/", 1)[1]
            status, j, raw = _mb("GET", f"/posts/{pid}", self.moltbook_key)
            return self._json(status if status else 502, j if j else {"raw": raw[:400]})

        return self._json(404, {"error": "not_found", "path": path})

    def do_POST(self):
        u = urlparse(self.path)
        path = u.path

        if not self._authed():
            return self._json(401, {"error": "unauthorized"})

        body = self._read_body()

        if path == "/moltbook/post-and-verify":
            title = (body.get("title") or "").strip()
            content = (body.get("body") or body.get("content") or "").strip()
            submolt = (body.get("submolt") or "general").strip()
            if not title or not content:
                return self._json(400, {"error": "title and body required"})
            r = mb_post_and_verify(self.moltbook_key, title, content, submolt)
            return self._json(200 if r.get("ok") else 500, r)

        if path == "/moltbook/comment-and-verify":
            pid = (body.get("post_id") or "").strip()
            content = (body.get("content") or "").strip()
            if not pid or not content:
                return self._json(400, {"error": "post_id and content required"})
            r = mb_comment_and_verify(self.moltbook_key, pid, content)
            return self._json(200 if r.get("ok") else 500, r)

        return self._json(404, {"error": "not_found", "path": path})

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()

    token = ensure_token()
    key = load_moltbook_key()

    Handler.moltbook_key = key
    Handler.worker_token = token

    addr = (args.host, args.port)
    httpd = ThreadingHTTPServer(addr, Handler)
    log.info("moltbook-worker listening on http://%s:%d", *addr)
    log.info("endpoints: POST /moltbook/{post-and-verify, comment-and-verify} · GET /moltbook/{home, profile, posts/:id} · GET /healthz")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log.info("shutting down")

if __name__ == "__main__":
    main()
