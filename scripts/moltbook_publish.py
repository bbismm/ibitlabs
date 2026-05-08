#!/usr/bin/env python3
"""Publish a post to Moltbook via REST API.

Persistent version of the session-scoped script that worked end-to-end on
2026-04-21. Captures the three API-shape facts and the CaSe-scrambled math
parser so future runs don't re-discover them:

  1. POST /api/v1/posts body field is `content`, NOT `body`.
  2. Verification data is nested under `post.verification.{verification_code,
     challenge_text}`.
  3. POST /api/v1/verify expects `{verification_code, answer}` as strings,
     with `answer` formatted "{:.2f}".

The math challenge text is case-scrambled (e.g. "loBsTeR eXeRts tHirTy-TwO
nEwToNs"). A naive split+lower fails — the parser here strips non-alpha then
greedy-matches the longest known token.

Rate limit: once per 2.5 minutes per account. Caller should back off on 429.

Usage:
    python3 moltbook_publish.py --title-file TITLE.txt --body-file BODY.txt \
        [--submolt trading] [--api-key $MOLTBOOK_API_KEY]

Exit codes: 0 success, 2 POST /posts failed, 3 /verify rejected (post deleted).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

API_BASE = "https://moltbook.com/api/v1"

IDEMPOTENCY_PATH = Path.home() / "Library" / "Application Support" / "ibitlabs" / "moltbook-publish-idempotency.json"
IDEMPOTENCY_WINDOW_SECONDS = 30 * 60  # 30 min — covers two scheduled-task ticks
IDEMPOTENCY_KEEP = 50  # keep last 50 records


def idempotency_key(submolt: str, title: str, body: str) -> str:
    blob = f"{submolt.strip()}\x00{title.strip()}\x00{body.strip()}".encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def _idempotency_load() -> list:
    if not IDEMPOTENCY_PATH.exists():
        return []
    try:
        return json.loads(IDEMPOTENCY_PATH.read_text())
    except Exception:
        return []


def _idempotency_save(records: list) -> None:
    IDEMPOTENCY_PATH.parent.mkdir(parents=True, exist_ok=True)
    trimmed = records[-IDEMPOTENCY_KEEP:]
    IDEMPOTENCY_PATH.write_text(json.dumps(trimmed, indent=2))


def idempotency_check(submolt: str, title: str, body: str) -> dict | None:
    """Return matching record dict if a duplicate within the window exists, else None."""
    key = idempotency_key(submolt, title, body)
    now = time.time()
    for rec in reversed(_idempotency_load()):
        if rec.get("key") == key and (now - rec.get("ts", 0)) < IDEMPOTENCY_WINDOW_SECONDS:
            return rec
    return None


def idempotency_record(submolt: str, title: str, body: str, post_id: str, url: str) -> None:
    records = _idempotency_load()
    records.append({
        "key": idempotency_key(submolt, title, body),
        "ts": int(time.time()),
        "submolt": submolt,
        "title": title[:120],
        "post_id": post_id,
        "url": url,
    })
    _idempotency_save(records)

# @ibitlabs_agent key — rotate here if the account changes.
# @ibitlabs_agent key — stored in macOS Keychain (rotated 2026-04-23 after
# a prior key was committed to a public repo). Fetch at runtime.
def _load_api_key_from_keychain():
    import subprocess
    try:
        out = subprocess.check_output(
            ["security", "find-generic-password",
             "-s", "ibitlabs-moltbook-agent",
             "-a", "ibitlabs", "-w"],
            stderr=subprocess.DEVNULL,
        ).decode("utf-8").strip()
        if out:
            return out
    except Exception:
        pass
    return None

DEFAULT_API_KEY = os.environ.get("MOLTBOOK_API_KEY") or _load_api_key_from_keychain() or ""
if not DEFAULT_API_KEY:
    import sys
    print("ERROR: No Moltbook API key found. Set MOLTBOOK_API_KEY env var or add to "
          "macOS Keychain: security add-generic-password -s ibitlabs-moltbook-agent "
          "-a ibitlabs -w '<KEY>'", file=sys.stderr)
    sys.exit(1)


NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
    "hundred": 100, "thousand": 1000,
}
ADD_VERBS = {
    # gain / gained / gains
    "gain", "gains", "gained", "gaining",
    # add
    "add", "adds", "added", "adding",
    # plus / and-as-operator handled separately
    "plus",
    # accelerate
    "accelerate", "accelerates", "accelerated", "accelerating",
    # speed up
    "speed", "speeds", "speedsup", "speedup", "sped", "speeding", "speedingup",
    "speedsupby", "speedupby",
    # increase
    "increase", "increases", "increased", "increasing",
    # rise
    "rise", "rises", "rose", "risen", "rising",
    # grow
    "grow", "grows", "grew", "grown", "growing",
    # climb
    "climb", "climbs", "climbed", "climbing",
    # other additive verbs
    "totals", "total", "combines", "combined", "sums", "summed",
}
SUB_VERBS = {
    # lose / lost
    "lose", "loses", "lost", "losing",
    # subtract
    "subtract", "subtracts", "subtracted", "subtracting",
    # minus
    "minus",
    # drop
    "drop", "drops", "dropped", "dropping",
    # slow / decelerate
    "slow", "slows", "slowed", "slowing",
    "decelerate", "decelerates", "decelerated", "decelerating",
    # molt (lobster-specific flavor)
    "molt", "molts", "molted", "molting",
    # decrease
    "decrease", "decreases", "decreased", "decreasing",
    # reduce
    "reduce", "reduces", "reduced", "reducing",
    # shrink
    "shrink", "shrinks", "shrank", "shrunk", "shrinking",
    # fall
    "fall", "falls", "fell", "fallen", "falling",
    # diminish
    "diminish", "diminishes", "diminished", "diminishing",
    # decline
    "decline", "declines", "declined", "declining",
    # sink
    "sink", "sinks", "sank", "sunk", "sinking",
    # reduction of force/velocity specific
    "subtracts", "lessens", "lessened", "lessen",
}
MUL_VERBS = {
    "times", "multiply", "multiplies", "multiplied", "multiplying",
    "doubles", "doubled", "triples", "tripled", "quadruples", "quadrupled",
}

# Words that look like number-word substrings and will false-match via fuzzy
# (e.g. "teen" ≠ 10 — it's the suffix of thirteen/fourteen/... Don't let
# levenshtein collapse it to "ten"). Same for "ty" as a suffix of tens.
FUZZY_NUMBER_BLACKLIST = {
    "teen", "ty", "en", "ne", "or", "in", "an", "on",
    "dred", "sand",  # partial hundred/thousand suffixes
    "urt", "ourt",   # partial "fourteen"/"forty" fragments
}


def http_json(method, url, api_key, body=None):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8")
            status = r.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        status = e.code
    except Exception as e:
        return 0, "", str(e)
    try:
        return status, raw, json.loads(raw)
    except Exception:
        return status, raw, None


def parse_number_sequence(tokens, i):
    if i >= len(tokens) or tokens[i].lower() not in NUMBER_WORDS:
        return None, i
    total = 0
    current = 0
    while i < len(tokens) and tokens[i].lower() in NUMBER_WORDS:
        n = NUMBER_WORDS[tokens[i].lower()]
        if n == 100:
            current = (current or 1) * 100
        elif n == 1000:
            total += (current or 1) * 1000
            current = 0
        else:
            current += n
        i += 1
    total += current
    return total, i


def compute_answer(challenge_text):
    """Parse a lobster-arithmetic challenge and return the answer as float.

    Respects word boundaries. Case-scramble may split a single token across
    punctuation/spaces (e.g. "sIxT y" → "sixty"), so we try joining 1..4
    consecutive word chunks. But we never match a token INSIDE a longer word
    (e.g. "ten" inside "antenna" must not match) — that was the 2026-04-23
    bug where a challenge containing "antenna push of fifteen newtons" was
    mis-parsed as 60 + 10 + 15 = 85 instead of 60 + 15 = 75.
    """
    text = (challenge_text or "").lower()
    # Replace non-alpha (except +/*) with a single space; preserves word boundaries.
    spaced = re.sub(r"[^a-z+*]+", " ", text).strip()
    raw_words = [w for w in spaced.split(" ") if w]
    # Keep +/* as their own pseudo-words.
    words: list[str] = []
    for w in raw_words:
        # operators come in as single chars; split them out if they're glued
        i = 0
        buf = ""
        while i < len(w):
            c = w[i]
            if c in "+*":
                if buf:
                    words.append(buf)
                    buf = ""
                words.append(c)
            else:
                buf += c
            i += 1
        if buf:
            words.append(buf)

    known_tokens = set(NUMBER_WORDS.keys()) | ADD_VERBS | SUB_VERBS | MUL_VERBS | {"and"}

    # Fuzzy match: allow 1-char edit distance for number words specifically
    # (handles case-scramble corruptions like "twenny"→"twenty", "tweenty"→"twenty",
    # "thirrty"→"thirty"). We ONLY fuzzy-match number words, not verbs, because
    # verb misspellings are rare and false matches on verbs break the arithmetic.
    def levenshtein(a: str, b: str) -> int:
        if abs(len(a) - len(b)) > 2:
            return 99
        m, n = len(a), len(b)
        prev = list(range(n + 1))
        for i in range(1, m + 1):
            curr = [i] + [0] * n
            for j in range(1, n + 1):
                cost = 0 if a[i-1] == b[j-1] else 1
                curr[j] = min(prev[j] + 1, curr[j-1] + 1, prev[j-1] + cost)
            prev = curr
        return prev[n]

    def dedup_consecutive(s):
        """Collapse runs of same letter: 'ttwweennttyy' → 'twenty'."""
        out = []
        for c in s:
            if not out or out[-1] != c:
                out.append(c)
        return ''.join(out)

    def fuzzy_number(word):
        if word in NUMBER_WORDS:
            return word
        if len(word) < 3:
            return None
        # Suffix fragments of compound number words (teen/ty/etc.) must NEVER
        # match — they are parts of "thirteen"/"twenty"/etc., not standalones.
        # Fixed 2026-04-23: "teen" was fuzzy-matching to "ten" and poisoning
        # sums. E.g. challenge "thirteen newtons" split word-wise as
        # ['t','hir','teen','newtons'] → the parser found 'thirteen' via join,
        # but in some scramble paths 'teen' stood alone and matched 'ten'.
        if word in FUZZY_NUMBER_BLACKLIST:
            return None
        # Lev ≤ 1 — but ONLY if first letter matches. This prevents false matches
        # like "fight"→"eight" (Lev=1 but different semantic) while still
        # allowing "twenny"→"twenty", "thirrty"→"thirty" (same first letter).
        for nw in NUMBER_WORDS:
            if (nw[0] == word[0]
                and abs(len(nw) - len(word)) <= 2
                and levenshtein(nw, word) <= 1):
                return nw
        # Dedup match (handles "ttwweennttyy"→"twenty", doubled-letter scramble).
        # Dedup doesn't risk false-positives like the Lev path, so no first-letter
        # constraint needed here (dedup is deterministic).
        w_dedup = dedup_consecutive(word)
        for nw in NUMBER_WORDS:
            if dedup_consecutive(nw) == w_dedup:
                return nw
        # REMOVED 2026-04-23: "Lev ≤ 1 on dedup'd forms" path was firing false
        # positives on 2-word fuzzy joins of garbage letters. Example: the
        # challenge "lobster exerts ... newtons" word-split into ['t','errr',...].
        # The 2-word-join path produced "terrr" which dedups to "ter", and Lev=1
        # from "ter" → "ten" triggered a spurious "ten" token that poisoned the
        # sum by +10. The exact-dedup path above already handles legit cases
        # like "twwennty" → "twenty". The Lev-on-dedup path was strictly
        # adding false matches, not catching legit ones.
        return None

    def fuzzy_verb(word, verb_set):
        """Fuzzy match verb tokens too, but only Lev ≤ 1 (conservative)."""
        if word in verb_set:
            return word
        if len(word) < 4:
            return None
        for v in verb_set:
            if abs(len(v) - len(word)) <= 1 and levenshtein(v, word) <= 1:
                return v
        # Dedup match for verbs
        w_dedup = dedup_consecutive(word)
        for v in verb_set:
            if dedup_consecutive(v) == w_dedup:
                return v
        return None

    tokens = []
    i = 0
    MAX_JOIN = 4  # handle case-scrambled "sIxT y" → "sixty" (2 chunks) up to 4
    while i < len(words):
        w = words[i]
        if w in ("+", "*"):
            tokens.append(w)
            i += 1
            continue
        # Try the longest exact join first, shrinking down to 1.
        best_k = 0
        best_tok = None
        for k in range(min(MAX_JOIN, len(words) - i), 0, -1):
            joined = "".join(words[i:i + k])
            if joined in known_tokens:
                best_k = k
                best_tok = joined
                break
        # If no exact match, try fuzzy-matching current word against number words
        # and verbs. Also try fuzzy-matching a join of 2 adjacent words (handles
        # doubled-letter scrambles that split "twenty" across word boundaries).
        if best_tok is None:
            fuzzy = fuzzy_number(w)
            if fuzzy:
                best_tok = fuzzy
                best_k = 1
        if best_tok is None:
            for vs in (ADD_VERBS, SUB_VERBS, MUL_VERBS):
                fv = fuzzy_verb(w, vs)
                if fv:
                    best_tok = fv
                    best_k = 1
                    break
        # Also try fuzzy-match on 2-word join (for scrambles that split a number
        # word like "tw ennttyy" across a space).
        if best_tok is None and i + 1 < len(words) and words[i+1] not in ("+", "*"):
            joined_2 = w + words[i+1]
            fz2 = fuzzy_number(joined_2)
            if fz2:
                best_tok = fz2
                best_k = 2
        if best_tok is not None:
            tokens.append(best_tok)
            i += best_k
        else:
            i += 1

    def apply_op(cur, operator, operand):
        if cur is None:
            return operand
        if operator == "+":
            return cur + operand
        if operator == "-":
            return cur - operand
        if operator == "*":
            return cur * operand
        return cur + operand

    result = None
    op = "+"
    j = 0
    while j < len(tokens):
        tok = tokens[j]
        if tok in NUMBER_WORDS:
            val, j_new = parse_number_sequence(tokens, j)
            if val is not None:
                result = apply_op(result, op, val)
                op = "+"
                j = j_new
                continue
        if tok == "+":
            op = "+"
            j += 1
            continue
        if tok == "*":
            op = "*"
            j += 1
            continue
        if tok in ADD_VERBS:
            op = "+"
            j += 1
            continue
        if tok in SUB_VERBS:
            op = "-"
            j += 1
            continue
        if tok in MUL_VERBS:
            op = "*"
            j += 1
            continue
        if tok == "and":
            nxt = tokens[j + 1] if j + 1 < len(tokens) else ""
            if nxt in ADD_VERBS or nxt in SUB_VERBS or nxt in MUL_VERBS:
                j += 1
                continue
            op = "+"
            j += 1
            continue
        j += 1

    print(f"DEBUG tokens: {tokens}")
    if result is None:
        return 0.0
    return float(result)


def main():
    ap = argparse.ArgumentParser(description="Publish a post to Moltbook")
    ap.add_argument("--title-file", required=True, help="Path to file containing post title")
    ap.add_argument("--body-file", required=True, help="Path to file containing post body")
    ap.add_argument("--submolt", default="trading", help="Submolt slug (default: trading)")
    ap.add_argument("--api-key", default=os.environ.get("MOLTBOOK_API_KEY", DEFAULT_API_KEY),
                    help="Moltbook API key (env MOLTBOOK_API_KEY or built-in default)")
    ap.add_argument("--result-file", default=None, help="Optional path to write result JSON")
    ap.add_argument("--allow-duplicate", action="store_true",
                    help="Bypass the 30-min idempotency check (only use if you intentionally want to re-publish identical content)")
    args = ap.parse_args()

    with open(args.title_file, "r", encoding="utf-8") as f:
        title = f.read().strip()
    with open(args.body_file, "r", encoding="utf-8") as f:
        body = f.read().strip()

    print(f"TITLE ({len(title)} chars): {title}")
    print(f"BODY ({len(body)} chars): first 120 → {body[:120]!r}")

    if not args.allow_duplicate:
        dup = idempotency_check(args.submolt, title, body)
        if dup is not None:
            age = int(time.time() - dup.get("ts", 0))
            print(f"DUPLICATE_DETECTED: same submolt+title+body posted {age}s ago "
                  f"as post_id={dup.get('post_id')} ({dup.get('url')}). "
                  f"Skipping POST. Use --allow-duplicate to override.", file=sys.stderr)
            if args.result_file:
                with open(args.result_file, "w") as f:
                    json.dump({"ok": False, "duplicate": True, "previous_post_id": dup.get("post_id"),
                               "previous_url": dup.get("url"), "age_seconds": age}, f, indent=2)
            sys.exit(6)

    payload = {"submolt": args.submolt, "title": title, "content": body}
    status, raw, parsed = http_json("POST", f"{API_BASE}/posts", args.api_key, payload)
    print(f"POST /posts → HTTP {status}")
    print(f"Response raw (full): {raw}")
    if status < 200 or status >= 300 or not isinstance(parsed, dict):
        print("FAIL: could not create post")
        sys.exit(2)

    post_obj = parsed.get("post") or {}
    post_id = post_obj.get("id") or parsed.get("id") or parsed.get("post_id")
    verif = post_obj.get("verification") or {}
    verification_code = (
        verif.get("verification_code")
        or post_obj.get("verification_code")
        or parsed.get("verification_code")
        or ""
    )
    challenge_text = (
        verif.get("challenge_text")
        or verif.get("challenge")
        or post_obj.get("math_challenge")
        or parsed.get("math_challenge")
        or ""
    )
    print(f"post_id: {post_id}")
    print(f"verification_code: {verification_code!r}")
    print(f"challenge: {challenge_text!r}")

    answer_float = compute_answer(challenge_text)
    answer_str = f"{round(answer_float, 2):.2f}"
    print(f"computed answer: {answer_float} → {answer_str}")

    verify_body = {"verification_code": str(verification_code), "answer": answer_str}
    verify_status, verify_raw, verify_parsed = http_json(
        "POST", f"{API_BASE}/verify", args.api_key, verify_body
    )
    print(f"POST /verify → HTTP {verify_status}")
    print(f"Verify raw: {verify_raw[:2000]}")
    if verify_status < 200 or verify_status >= 300:
        print("FAIL: verify rejected — deleting post")
        del_status, del_raw, _ = http_json("DELETE", f"{API_BASE}/posts/{post_id}", args.api_key)
        print(f"DELETE /posts/{post_id} → HTTP {del_status}, {del_raw[:300]}")
        sys.exit(3)

    url = f"https://moltbook.com/post/{post_id}"
    print(f"SUCCESS: {url}")

    try:
        idempotency_record(args.submolt, title, body, str(post_id), url)
    except Exception as e:
        print(f"WARN: idempotency_record failed (post still succeeded): {e}", file=sys.stderr)

    if args.result_file:
        out = {
            "post_id": post_id,
            "url": url,
            "verify_status": verify_status,
            "verify_body": verify_parsed if verify_parsed else verify_raw[:500],
        }
        with open(args.result_file, "w") as f:
            json.dump(out, f, indent=2)


if __name__ == "__main__":
    main()
