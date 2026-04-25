"""HMAC-SHA256 JWT minimal implementation.

避免引入 pyjwt 的额外依赖。仅支持 HS256 + 我们自己的 payload schema。

Token format: <header>.<payload>.<signature>
  header    = b64url({"alg":"HS256","typ":"JWT"})
  payload   = b64url(json(claims))
  signature = b64url(HMAC_SHA256(secret, header + "." + payload))
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any


_HEADER = b'{"alg":"HS256","typ":"JWT"}'


def _b64encode(raw: bytes) -> str:
    """URL-safe base64 without padding."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(s: str) -> bytes:
    pad = "=" * ((4 - len(s) % 4) % 4)
    return base64.urlsafe_b64decode(s + pad)


def make_jwt(payload: dict[str, Any], secret: str) -> str:
    """Sign a payload with HMAC-SHA256, return JWT string."""
    p1 = _b64encode(_HEADER)
    p2 = _b64encode(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(
        secret.encode(), f"{p1}.{p2}".encode(), hashlib.sha256
    ).digest()
    p3 = _b64encode(sig)
    return f"{p1}.{p2}.{p3}"


def verify_jwt(token: str, secret: str) -> dict[str, Any] | None:
    """Verify signature and return payload dict, or None if invalid/expired."""
    if not token or not isinstance(token, str):
        return None
    parts = token.split(".")
    if len(parts) != 3:
        return None
    p1, p2, p3 = parts
    try:
        expected = hmac.new(
            secret.encode(), f"{p1}.{p2}".encode(), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(_b64encode(expected), p3):
            return None
        payload: dict[str, Any] = json.loads(_b64decode(p2))
    except Exception:
        return None
    # exp check (unix epoch seconds)
    exp = payload.get("exp")
    if isinstance(exp, (int, float)) and exp < time.time():
        return None
    return payload


def hash_secret(secret: str) -> str:
    """SHA256 of secret, hex-encoded. Used for logging/comparison without exposing secret."""
    return hashlib.sha256(secret.encode()).hexdigest()
