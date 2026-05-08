"""
Shared access code verification — used by Tier 3 (Paid Signals) and Tier 4 (Copy Trading).
Supports two code types:
  1. Static codes from access_codes.json
  2. Dynamic codes from Cloudflare KV (BA-XXXXXXXX, generated on Stripe payment)
"""

import json
import os
import time
import logging
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

logger = logging.getLogger(__name__)

ACCESS_FILE = Path(__file__).parent / "access_codes.json"

# Cache for KV-validated codes: {code: (valid, timestamp)}
_kv_cache = {}
KV_CACHE_TTL = 300  # 5 minutes

VALIDATE_URL = os.environ.get("VALIDATE_CODE_URL", "https://ibitlabs.com/api/validate-code")


def verify_access(code: str) -> bool:
    """Check if access code is valid. Supports static + KV-backed codes."""
    if not code:
        return False

    code = code.strip().upper()

    # Check static codes first (fast, no network)
    try:
        with open(ACCESS_FILE) as f:
            data = json.load(f)
        entry = data.get("codes", {}).get(code)
        if entry:
            expires = datetime.strptime(entry["expires"], "%Y-%m-%d")
            if datetime.now() <= expires:
                return True
    except Exception:
        pass

    # For KV-generated codes (BA-XXXXXXXX), validate via Cloudflare API
    if code.startswith("BA-"):
        return _verify_kv_code(code)

    return False


def _verify_kv_code(code: str) -> bool:
    """Validate a KV-backed access code via the Cloudflare Function."""
    now = time.time()

    # Check cache
    if code in _kv_cache:
        valid, ts = _kv_cache[code]
        if now - ts < KV_CACHE_TTL:
            return valid

    try:
        url = f"{VALIDATE_URL}?code={code}"
        req = Request(url, headers={"User-Agent": "BibsusSignals/1.0"})
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            valid = data.get("valid", False)
            _kv_cache[code] = (valid, now)
            return valid
    except (URLError, json.JSONDecodeError, Exception) as e:
        logger.warning(f"KV validation failed for {code[:6]}...: {e}")
        # Fail closed — if we can't verify, deny access
        return False
