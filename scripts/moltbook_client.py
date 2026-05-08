#!/usr/bin/env python3
"""
moltbook_client.py — Sandbox-side client for the host moltbook-worker.

Use this from inside the Cowork Linux sandbox (where macOS Keychain is
unreachable) to publish/comment/read on Moltbook via the host worker
running on the Mac.

Wire-up:
  - Worker URL:       http://host.docker.internal:8765  (override with MOLTBOOK_WORKER_URL)
  - Auth:             Bearer token in MOLTBOOK_WORKER_TOKEN env var
  - Healthcheck:      `python3 moltbook_client.py health`
  - Publish post:     `python3 moltbook_client.py post --title-file T --body-file B [--submolt general]`
  - Comment:          `python3 moltbook_client.py comment --post-id ID --content-file C`
  - Get profile:      `python3 moltbook_client.py profile --name ibitlabs_agent`
  - Get post:         `python3 moltbook_client.py get-post --post-id ID`
  - Get home:         `python3 moltbook_client.py home`

Exit codes match moltbook_publish.py contract for drop-in compatibility:
  0 — success (writes JSON to --result-file if given)
  2 — POST/HTTP failure (do NOT retry)
  3 — verify failed and post deleted (ONE retry OK)
  4 — rate limited (sleep retry_after_seconds and retry)
  5 — auth/config error (worker unreachable, token missing, etc.)
"""

from __future__ import annotations
import argparse
import json
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEFAULT_WORKER_URL = os.environ.get("MOLTBOOK_WORKER_URL", "http://host.docker.internal:8765")
TOKEN = os.environ.get("MOLTBOOK_WORKER_TOKEN", "").strip()


def _die(exit_code: int, msg: str, payload: dict | None = None) -> None:
    out = {"ok": False, "error": msg}
    if payload:
        out.update(payload)
    print(json.dumps(out), file=sys.stderr)
    sys.exit(exit_code)


def _require_token() -> None:
    if not TOKEN:
        _die(5, "MOLTBOOK_WORKER_TOKEN env var not set; retrieve from Mac host: "
                "cat ~/Library/Application\\ Support/ibitlabs/moltbook-worker.token")


def _call(method: str, path: str, body: dict | None = None, timeout: int = 30) -> tuple[int, dict | None, str]:
    url = f"{DEFAULT_WORKER_URL.rstrip('/')}{path}"
    req = Request(url, method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    data = None
    if body is not None:
        req.add_header("Content-Type", "application/json")
        data = json.dumps(body).encode("utf-8")
    try:
        with urlopen(req, data=data, timeout=timeout) as r:
            raw = r.read().decode("utf-8", errors="replace")
            try:
                return r.status, json.loads(raw), raw
            except Exception:
                return r.status, None, raw
    except HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(raw), raw
        except Exception:
            return e.code, None, raw
    except URLError as e:
        return 0, None, f"unreachable: {e.reason}"
    except Exception as e:
        return 0, None, f"transport_error: {e}"


def _read_text_arg(args, file_attr: str, inline_attr: str | None = None, max_bytes: int = 80_000) -> str:
    fp = getattr(args, file_attr, None)
    if fp:
        with open(fp, "r", encoding="utf-8") as f:
            txt = f.read()
        if len(txt.encode("utf-8")) > max_bytes:
            _die(2, f"{file_attr} exceeds {max_bytes} bytes")
        return txt.strip()
    if inline_attr:
        v = getattr(args, inline_attr, None)
        if v:
            return v.strip()
    _die(2, f"missing --{file_attr.replace('_','-')}")
    return ""  # unreachable


def _write_result(path: str | None, payload: dict) -> None:
    if path:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)


# ─── Commands ────────────────────────────────────────────────────────
def cmd_health(_args) -> int:
    status, j, raw = _call("GET", "/healthz")
    if status == 200:
        print(json.dumps(j or {"raw": raw}, indent=2))
        return 0
    print(f"unhealthy: status={status} body={raw[:300]}", file=sys.stderr)
    return 5


def cmd_post(args) -> int:
    _require_token()
    title = _read_text_arg(args, "title_file", "title", max_bytes=400)
    body = _read_text_arg(args, "body_file", "body", max_bytes=80_000)
    payload = {"title": title, "body": body, "submolt": args.submolt}
    status, j, raw = _call("POST", "/moltbook/post-and-verify", payload, timeout=60)
    if status == 0:
        _die(5, "worker unreachable", {"raw": raw[:300]})
    if not j:
        _die(2, f"non-JSON response (status={status})", {"raw": raw[:300]})
    _write_result(args.result_file, j)
    if j.get("ok"):
        print(j.get("url") or json.dumps(j))
        return 0
    err = j.get("error", "")
    if "rate_limited" in err:
        print(json.dumps(j), file=sys.stderr)
        return 4
    if err.startswith("verify_") or err.startswith("parse_challenge"):
        print(json.dumps(j), file=sys.stderr)
        return 3
    print(json.dumps(j), file=sys.stderr)
    return 2


def cmd_comment(args) -> int:
    _require_token()
    content = _read_text_arg(args, "content_file", "content", max_bytes=10_000)
    payload = {"post_id": args.post_id, "content": content}
    status, j, raw = _call("POST", "/moltbook/comment-and-verify", payload, timeout=60)
    if status == 0:
        _die(5, "worker unreachable", {"raw": raw[:300]})
    if not j:
        _die(2, f"non-JSON response (status={status})", {"raw": raw[:300]})
    _write_result(args.result_file, j)
    if j.get("ok"):
        print(json.dumps(j))
        return 0
    err = j.get("error", "")
    if "rate_limited" in err:
        return 4
    if err.startswith("verify_"):
        return 3
    print(json.dumps(j), file=sys.stderr)
    return 2


def cmd_profile(args) -> int:
    _require_token()
    qs = urlencode({"name": args.name})
    status, j, raw = _call("GET", f"/moltbook/profile?{qs}")
    print(json.dumps(j if j else {"raw": raw[:600]}, indent=2))
    return 0 if status == 200 else 2


def cmd_get_post(args) -> int:
    _require_token()
    status, j, raw = _call("GET", f"/moltbook/posts/{args.post_id}")
    print(json.dumps(j if j else {"raw": raw[:600]}, indent=2))
    return 0 if status == 200 else 2


def cmd_home(_args) -> int:
    _require_token()
    status, j, raw = _call("GET", "/moltbook/home")
    print(json.dumps(j if j else {"raw": raw[:600]}, indent=2))
    return 0 if status == 200 else 2


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--worker-url", default=None, help=f"override worker URL (default: {DEFAULT_WORKER_URL})")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("health"); sp.set_defaults(func=cmd_health)

    sp = sub.add_parser("post")
    sp.add_argument("--title-file"); sp.add_argument("--title")
    sp.add_argument("--body-file"); sp.add_argument("--body")
    sp.add_argument("--submolt", default="general")
    sp.add_argument("--result-file")
    sp.set_defaults(func=cmd_post)

    sp = sub.add_parser("comment")
    sp.add_argument("--post-id", required=True)
    sp.add_argument("--content-file"); sp.add_argument("--content")
    sp.add_argument("--result-file")
    sp.set_defaults(func=cmd_comment)

    sp = sub.add_parser("profile")
    sp.add_argument("--name", required=True)
    sp.set_defaults(func=cmd_profile)

    sp = sub.add_parser("get-post")
    sp.add_argument("--post-id", required=True)
    sp.set_defaults(func=cmd_get_post)

    sp = sub.add_parser("home")
    sp.set_defaults(func=cmd_home)

    args = p.parse_args()
    if args.worker_url:
        global DEFAULT_WORKER_URL
        DEFAULT_WORKER_URL = args.worker_url
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
