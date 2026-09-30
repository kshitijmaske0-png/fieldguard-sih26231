"""Canonical JSON, SHA-256 hash, Ed25519 signature, hash chain.

Limit to state honestly: the server signs, so this makes changes AFTER the fact detectable.
It does not prove the server was honest when it signed (that is what external timestamp
anchoring, e.g. RFC 3161, would add: listed as future scope)."""
import hashlib, json, sys
from nacl.signing import SigningKey, VerifyKey
from .config import GENESIS_HASH, signing_key_hex


def canonical(d):
    return json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def load_signing_key() -> SigningKey:
    return SigningKey(bytes.fromhex(signing_key_hex()))


def public_key_hex(sk: SigningKey = None) -> str:
    return (sk or load_signing_key()).verify_key.encode().hex()


def make_record(fields, prev_hash, signing_key: SigningKey):
    body = {**fields, "prev_hash": prev_hash}
    h = hashlib.sha256(canonical(body)).hexdigest()
    sig = signing_key.sign(bytes.fromhex(h)).signature.hex()
    return {**body, "record_hash": h, "signature": sig}


def verify_record(rec, verify_key: VerifyKey):
    body = {k: v for k, v in rec.items() if k not in ("record_hash", "signature")}
    h = hashlib.sha256(canonical(body)).hexdigest()
    if h != rec.get("record_hash"):
        return False
    try:
        verify_key.verify(bytes.fromhex(h), bytes.fromhex(rec["signature"]))
        return True
    except Exception:
        return False


def verify_chain(records_in_order, verify_key: VerifyKey):
    """records_in_order: list of record dicts, oldest first. Returns (ok, first_bad_index, reason)."""
    prev = GENESIS_HASH
    for i, rec in enumerate(records_in_order):
        if rec.get("prev_hash") != prev:
            return False, i, "chain link broken (record removed, inserted or reordered)"
        if not verify_record(rec, verify_key):
            return False, i, "hash or signature mismatch (record edited)"
        prev = rec["record_hash"]
    return True, None, "ok"


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "genkey":
        print(SigningKey.generate().encode().hex())     # export as FIELDGUARD_SIGNING_KEY
    else:
        print("usage: python -m backend.records genkey")
