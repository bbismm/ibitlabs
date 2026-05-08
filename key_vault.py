"""
Key Vault — encrypts/decrypts customer API keys using Fernet (AES-128-CBC + HMAC).
Master key from AUTOPILOT_MASTER_KEY env var. Each customer stored as customer_keys/{id}.enc.

API keys are NEVER logged, returned via API, or stored in plaintext.
"""

import json
import os
import base64
import hashlib
import logging
from pathlib import Path

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

KEYS_DIR = Path(__file__).parent / "customer_keys"
KEYS_DIR.mkdir(exist_ok=True)

# Salt for PBKDF2 key derivation (fixed per installation)
_SALT = b"bibsus-copy-trading-v1"


def _get_fernet() -> Fernet:
    """Derive Fernet key from AUTOPILOT_MASTER_KEY env var."""
    master = os.environ.get("AUTOPILOT_MASTER_KEY", "")
    if not master:
        raise ValueError("AUTOPILOT_MASTER_KEY environment variable not set")
    # Derive 32-byte key via PBKDF2
    key_bytes = hashlib.pbkdf2_hmac("sha256", master.encode(), _SALT, 100_000)
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    return Fernet(fernet_key)


def store(customer_id: str, api_key: str, api_secret: str) -> None:
    """Encrypt and store customer API credentials."""
    f = _get_fernet()
    payload = json.dumps({"api_key": api_key, "api_secret": api_secret}).encode()
    encrypted = f.encrypt(payload)
    filepath = KEYS_DIR / f"{customer_id}.enc"
    filepath.write_bytes(encrypted)
    logger.info(f"Stored encrypted keys for customer {customer_id}")


def load(customer_id: str) -> tuple[str, str]:
    """Decrypt and return (api_key, api_secret) for a customer."""
    filepath = KEYS_DIR / f"{customer_id}.enc"
    if not filepath.exists():
        raise FileNotFoundError(f"No keys for customer {customer_id}")
    f = _get_fernet()
    encrypted = filepath.read_bytes()
    decrypted = json.loads(f.decrypt(encrypted))
    return decrypted["api_key"], decrypted["api_secret"]


def delete(customer_id: str) -> None:
    """Remove a customer's encrypted key file."""
    filepath = KEYS_DIR / f"{customer_id}.enc"
    if filepath.exists():
        filepath.unlink()
        logger.info(f"Deleted keys for customer {customer_id}")
