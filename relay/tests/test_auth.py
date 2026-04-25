"""Tests for auth.make_jwt / verify_jwt"""
import sys
import time
from pathlib import Path

# Allow importing parent module
sys.path.insert(0, str(Path(__file__).parent.parent))

from auth import make_jwt, verify_jwt, hash_secret


SECRET = "test-secret-please-change-32-bytes-min"


def test_round_trip():
    token = make_jwt({"tid": "t1", "kind": "hub", "exp": int(time.time()) + 60}, SECRET)
    payload = verify_jwt(token, SECRET)
    assert payload is not None
    assert payload["tid"] == "t1"
    assert payload["kind"] == "hub"


def test_wrong_secret_rejected():
    token = make_jwt({"tid": "t1"}, SECRET)
    assert verify_jwt(token, "different-secret-32-byte-min-value") is None


def test_expired_rejected():
    token = make_jwt({"tid": "t1", "exp": int(time.time()) - 10}, SECRET)
    assert verify_jwt(token, SECRET) is None


def test_no_exp_ok():
    token = make_jwt({"tid": "t1"}, SECRET)
    assert verify_jwt(token, SECRET) is not None


def test_garbled_token():
    assert verify_jwt("not-a-jwt", SECRET) is None
    assert verify_jwt("a.b.c", SECRET) is None
    assert verify_jwt("", SECRET) is None
    assert verify_jwt(None, SECRET) is None  # type: ignore


def test_tampered_payload():
    token = make_jwt({"tid": "t1", "kind": "client"}, SECRET)
    parts = token.split(".")
    # Modify payload — signature won't match
    tampered = f"{parts[0]}.AAAA.{parts[2]}"
    assert verify_jwt(tampered, SECRET) is None


def test_hash_secret_deterministic():
    h1 = hash_secret("foo")
    h2 = hash_secret("foo")
    h3 = hash_secret("bar")
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 64  # sha256 hex


if __name__ == "__main__":
    test_round_trip()
    test_wrong_secret_rejected()
    test_expired_rejected()
    test_no_exp_ok()
    test_garbled_token()
    test_tampered_payload()
    test_hash_secret_deterministic()
    print("✅ all auth tests passed")
