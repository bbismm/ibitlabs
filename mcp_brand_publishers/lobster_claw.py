"""
Lobster-claw verification parser for Moltbook /api/v1/verify.

Per SKILL.md spec:
    Parser keeps only [A-Za-z+*], lowercases, greedy-matches longest known
    token from number words (zero..thousand), ADD_VERBS (gains/adds/plus),
    SUB_VERBS (loses/drops/molts), MUL_VERBS (times/multiplied), "and".
    Evaluate left-to-right. Format as {:.2f}.

Pure module: no network, no I/O. Imported by server.py and exercised by
test_lobster_claw.py.
"""

from __future__ import annotations
import re

# Number-word vocabulary (zero..thousand)
NUMBER_WORDS: dict[str, int] = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    "hundred": 100, "thousand": 1000,
}

ADD_VERBS = {"gains", "adds", "plus"}
SUB_VERBS = {"loses", "drops", "molts", "slows"}
MUL_VERBS = {"times", "multiplied", "multiply", "multiplies"}
SEPARATORS = {"and"}

# Postfix math nouns: "what is the <noun> of A and B" → A <op> B.
# Added 2026-04-26 after a real challenge ("what is the product of these")
# returned 40 instead of 364 in production. The infix parser cannot handle
# operator-after-operands phrasing, so these get a separate code path.
POSTFIX_NOUNS: dict[str, str] = {
    "product": "*",
    "sum": "+",
    "total": "+",
    "difference": "-",
    "quotient": "/",
}

# Pre-built sorted token list, longest first, for greedy matching.
_ALL_TOKENS: list[str] = sorted(
    set(NUMBER_WORDS.keys())
    | ADD_VERBS
    | SUB_VERBS
    | MUL_VERBS
    | SEPARATORS
    | set(POSTFIX_NOUNS.keys())
    | {"+", "*"},
    key=len,
    reverse=True,
)


def _clean(challenge: str) -> str:
    """Keep only [A-Za-z+*], lowercase. Per SKILL.md.

    Also collapses repeated a/i/o/u (obfuscation artifact from the mixed-case
    challenge style — e.g. "SlOoWs" cleans to "sloows"; normalizing gives
    "slows" so the token matches). 'e' is excluded: number words like "fifteen"
    and "seventeen" contain "ee" and must not be collapsed.
    """
    s = re.sub(r"[^A-Za-z+*]", "", challenge).lower()
    return re.sub(r"([aiou])\1+", r"\1", s)


def _tokenize(cleaned: str) -> list[str]:
    """Greedy-match longest known token. Skip unknown chars."""
    tokens: list[str] = []
    i = 0
    n = len(cleaned)
    while i < n:
        matched: str | None = None
        for tok in _ALL_TOKENS:
            tlen = len(tok)
            if cleaned[i : i + tlen] == tok:
                matched = tok
                break
        if matched is None:
            i += 1
        else:
            tokens.append(matched)
            i += len(matched)
    return tokens


def _fold_compound(num_tokens: list[str]) -> int:
    """
    Fold a run of number words into a single integer.

    Handles English compound forms:
        "twenty one"        -> 21
        "two hundred"       -> 200
        "two hundred three" -> 203
        "one thousand five hundred twenty one" -> 1521

    Adjacent small-number words without a multiplier are summed conservatively:
        "five seven" -> 12
    The challenge generator does not currently emit that pattern but the
    parser stays defensive.
    """
    total = 0
    current = 0
    for w in num_tokens:
        v = NUMBER_WORDS[w]
        if v == 100 or v == 1000:
            # multiplier: scale the current accumulator (or 1 if empty)
            current = (current or 1) * v
            if v == 1000:
                # "one thousand X hundred Y" — 1000 closes a magnitude block
                total += current
                current = 0
        else:
            current += v
    return total + current


def _postfix_solve(challenge: str, tokens: list[str]) -> str | None:
    """
    Try the postfix-noun path: "what is the <product|sum|...> of A and B" ->
    op(A, B). Returns the formatted answer if a postfix noun is present and at
    least two operand groups can be parsed; otherwise returns None and the
    caller falls back to the infix path.

    Operand grouping: "and" between two compound numbers normally acts as a
    no-op joiner ("two hundred and three" -> 203). In postfix mode, "and"
    only stays a no-op when the previous number word was a magnitude
    (hundred/thousand); otherwise it is a separator between operand groups.
    Any non-number, non-"and" token (verbs, the postfix noun itself, +, *)
    also flushes the current operand group.

    Whole-word check: the postfix noun must appear as a whole word in the
    original (uncleaned) challenge. Otherwise common substrings like
    "summons" / "summer" / "totally" / "consumed" would falsely trigger the
    postfix path (the greedy tokenizer finds "sum" inside "summons" etc.,
    which is fine for infix where unknown verb-tokens are silently dropped,
    but catastrophic in postfix mode where it changes the operator).

    If multiple distinct postfix ops appear in the same challenge, returns
    None (ambiguous; defer to infix).
    """
    # If explicit operator symbols appear in the token list, the infix path
    # handles them correctly. Don't let a postfix noun override an explicit
    # operator — e.g. "forty * two claws, how much total force?" should
    # multiply (infix), not add (postfix "total" → "+").
    if "+" in tokens or "*" in tokens:
        return None

    op_tokens = [t for t in tokens if t in POSTFIX_NOUNS]
    if not op_tokens:
        return None
    # Whole-word filter against the raw challenge (case-insensitive).
    op_tokens = [
        t for t in op_tokens
        if re.search(rf"\b{t}\b", challenge, re.IGNORECASE) is not None
    ]
    if not op_tokens:
        return None
    distinct_ops = {POSTFIX_NOUNS[t] for t in op_tokens}
    if len(distinct_ops) > 1:
        return None
    op = POSTFIX_NOUNS[op_tokens[0]]

    groups: list[int] = []
    buf: list[str] = []
    last_num: str | None = None

    def flush() -> None:
        nonlocal last_num
        if buf:
            groups.append(_fold_compound(buf))
            buf.clear()
        last_num = None

    # Use gap-aware tokens so "thirty [notonswith] one" does not fold to 31:
    # a gap between non-adjacent number tokens breaks the compound buffer.
    gap_tokens = _tokenize_with_gaps(_clean(challenge))
    for tok in gap_tokens:
        if tok == "__GAP__":
            # Non-adjacent gap: break compound if last_num is not a magnitude.
            # Prevents "thirty [stuff] one" → 31; "twenty" + adjacent "two" → 22 still works.
            if buf and NUMBER_WORDS.get(last_num, 0) not in (100, 1000):
                flush()
        elif tok in NUMBER_WORDS:
            buf.append(tok)
            last_num = tok
        elif tok in SEPARATORS:
            # "and" after a magnitude word stays a compound joiner; otherwise
            # it separates operand groups.
            if last_num in {"hundred", "thousand"}:
                continue
            flush()
        else:
            # Verb / postfix noun / "+" / "*" — all act as group boundaries
            # in postfix mode.
            flush()
    flush()

    if len(groups) < 2:
        return None  # need at least two operands to apply a postfix op

    # Drop likely modifier-ones: "thirty Newtons with ONE claw" emits groups [30, 1, 22]
    # when "one" refers to claw count, not force. Filter: if ≥3 groups exist, some are 1,
    # and ≥2 others are ≥10, the 1-groups are count modifiers, not force operands.
    if len(groups) >= 3:
        non_one = [g for g in groups if g != 1]
        if len(non_one) >= 2 and all(v >= 10 for v in non_one):
            groups = non_one

    if len(groups) < 2:
        return None

    result: float = float(groups[0])
    for v in groups[1:]:
        if op == "+":
            result += v
        elif op == "-":
            result -= v
        elif op == "*":
            result *= v
        elif op == "/":
            if v == 0:
                return None  # bail; let infix path / caller handle
            result /= v
    return f"{result:.2f}"


def _debug_log(challenge: str, cleaned: str, tokens: list[str],
                pairs_or_postfix: object, answer: str | None,
                error: str | None = None) -> None:
    """
    Append every solve() invocation to ~/ibitlabs/logs/lobster_claw_debug.jsonl.

    Added 2026-04-28 after a production challenge gave 35-12=24 (off by 1)
    that the test corpus does not cover. Without the raw challenge text we
    cannot reproduce; this log captures it on the next failure (and every
    success), turning each cron invocation into a corpus row.

    Best-effort — never raises. Disk write failures are silently swallowed.
    """
    try:
        import os, json, time
        path = os.path.expanduser("~/ibitlabs/logs/lobster_claw_debug.jsonl")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        row = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "challenge": challenge,
            "cleaned": cleaned,
            "tokens": tokens,
            "result": pairs_or_postfix if not isinstance(pairs_or_postfix, list) else [(o, v) for o, v in pairs_or_postfix],
            "answer": answer,
            "error": error,
        }
        with open(path, "a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass  # never break the executor


def _infix_pairs(tokens: list[str]) -> list[tuple[str, int]]:
    """
    Extract (op, value) pairs from a token list using infix parsing.
    Returns [] if no number tokens are found.
    """
    pairs: list[tuple[str, int]] = []
    pending_op = "+"
    buf: list[str] = []

    def flush() -> None:
        if buf:
            pairs.append((pending_op, _fold_compound(buf)))
            buf.clear()

    for tok in tokens:
        if tok in NUMBER_WORDS:
            buf.append(tok)
        elif tok in SEPARATORS:
            continue
        elif tok in ADD_VERBS or tok == "+":
            flush()
            pending_op = "+"
        elif tok in SUB_VERBS:
            flush()
            pending_op = "-"
        elif tok in MUL_VERBS or tok == "*":
            flush()
            pending_op = "*"
    flush()
    return pairs


def _tokenize_with_gaps(cleaned: str) -> list[str]:
    """Like _tokenize but inserts '__GAP__' between tokens separated by non-matching chars.

    Used by _postfix_solve to prevent "thirty [notons with] one" from being
    folded into compound 31: the gap between 'thirty' and 'one' triggers a
    buffer flush so they remain separate operand groups.
    """
    tokens: list[str] = []
    i = 0
    n = len(cleaned)
    had_gap = False
    while i < n:
        matched: str | None = None
        for tok in _ALL_TOKENS:
            tlen = len(tok)
            if cleaned[i : i + tlen] == tok:
                matched = tok
                break
        if matched is None:
            i += 1
            had_gap = True
        else:
            if had_gap and tokens:
                tokens.append("__GAP__")
            tokens.append(matched)
            had_gap = False
            i += len(matched)
    return tokens


# Pre-built doubled-char token patterns (longest first) — cached at module load.
# Each token char is wrapped in `char{1,2}` so "twenty" matches "twweennttyyy".
# Used by _tokenize_doubled() as the fallback path for doubled-char obfuscation.
_DOUBLED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile("".join(f"{re.escape(c)}{{1,2}}" for c in tok)), tok)
    for tok in _ALL_TOKENS
]


def _tokenize_doubled(cleaned: str) -> list[str]:
    """
    Tokenize a string where each character of the original word may appear
    1 or 2 times consecutively (doubled-char obfuscation).

    Examples:
      "twweennttyyy"  → ["twenty"]   (each char doubled)
      "thhree"        → ["three"]    (only 'h' doubled; 'ee' natural)
      "fiivvee"       → ["five"]     (i,v,e each doubled)

    Falls back to skip (i += 1) for unrecognised characters, same as _tokenize().
    """
    tokens: list[str] = []
    i = 0
    n = len(cleaned)
    while i < n:
        matched_tok: str | None = None
        matched_len: int = 0
        for pattern, tok in _DOUBLED_PATTERNS:
            m = pattern.match(cleaned, i)
            if m:
                matched_tok = tok
                matched_len = m.end() - m.start()
                break
        if matched_tok is None:
            i += 1
        else:
            tokens.append(matched_tok)
            i += matched_len
    return tokens


def solve(challenge: str) -> str:
    """
    Solve a lobster-claw challenge, return the answer formatted as "{:.2f}".

    Two-pass strategy: standard clean first; if no operands, retry with
    full-collapse clean that also handles doubled-consonant obfuscation.

    Raises ValueError if no operands are found after both passes.
    """
    cleaned = _clean(challenge)
    tokens = _tokenize(cleaned)

    # Postfix-noun path takes priority: "what is the product of A and B".
    postfix = _postfix_solve(challenge, tokens)
    if postfix is not None:
        _debug_log(challenge, cleaned, tokens, "postfix", postfix)
        return postfix

    pairs = _infix_pairs(tokens)

    if not pairs:
        # Fallback: doubled-char obfuscation (e.g. 'tWwEeNnTtYy' where each
        # original char appears 1–2 times). Re-tokenize with char{1,2} patterns
        # so "twenty" matches "twweennttyyy" and "three" still matches "thhree"
        # without collapsing the natural 'ee' at the end of "three".
        tokens2 = _tokenize_doubled(cleaned)

        postfix2 = _postfix_solve(challenge, tokens2)
        if postfix2 is not None:
            _debug_log(challenge, cleaned, tokens2, "postfix_fallback", postfix2)
            return postfix2

        pairs = _infix_pairs(tokens2)

    if not pairs:
        _debug_log(challenge, cleaned, tokens, [], None,
                   error="no operands parsed")
        raise ValueError(f"no operands parsed from challenge: {challenge!r}")

    # Strict left-to-right evaluation (no operator precedence).
    result: float = float(pairs[0][1])
    for op, val in pairs[1:]:
        if op == "+":
            result += val
        elif op == "-":
            result -= val
        elif op == "*":
            result *= val
        else:  # pragma: no cover - defensive
            raise ValueError(f"unknown operator: {op!r}")

    answer = f"{result:.2f}"
    _debug_log(challenge, cleaned, tokens, pairs, answer)
    return answer


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("usage: python lobster_claw.py <challenge text>", file=sys.stderr)
        sys.exit(2)
    print(solve(" ".join(sys.argv[1:])))
