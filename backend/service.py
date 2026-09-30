"""Business logic, independent of the web framework (so it can be unit-tested)."""
import hashlib, json, uuid
from datetime import date, datetime, timezone
from pathlib import Path

from . import db, vision
from .config import UPLOAD_DIR, MAX_UPLOAD_BYTES, GENESIS_HASH, load_kits
from .records import make_record, verify_record, load_signing_key, public_key_hex


class ServiceError(Exception):
    def __init__(self, status, message):
        super().__init__(message); self.status, self.message = status, message


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _image_ext(b):
    if b[:3] == b"\xff\xd8\xff": return ".jpg"
    if b[:8] == b"\x89PNG\r\n\x1a\n": return ".png"
    raise ServiceError(422, "Photo must be a JPEG or PNG image")


def create_test(user, photo_bytes, kit_type, kit_lot, kit_expiry, control_done, timer_seconds,
                gps=None, client_time=None, device_id="unknown"):
    kits = load_kits()
    kit = kits["kits"].get(kit_type)
    if not kit:
        raise ServiceError(422, "Unknown kit type")
    kit_lot = (kit_lot or "").strip()
    if not kit_lot or len(kit_lot) > 64:
        raise ServiceError(422, "Kit lot number is required")
    try:
        expiry = date.fromisoformat(kit_expiry)
    except Exception:
        raise ServiceError(422, "Kit expiry must be a date (YYYY-MM-DD)")
    if expiry < datetime.now(timezone.utc).date():
        raise ServiceError(422, f"Kit expired on {expiry.isoformat()}: test blocked")
    if not control_done:
        raise ServiceError(422, "Control step must be completed before the test")
    window = int(kit["reading_window_s"])
    if timer_seconds < window:
        raise ServiceError(422, f"Reading window not completed ({window}s required)")
    if len(photo_bytes) > MAX_UPLOAD_BYTES:
        raise ServiceError(413, "Photo too large")
    ext = _image_ext(photo_bytes)

    analysis = vision.analyse(photo_bytes, kit)
    if analysis["status"] != "OK":                      # RETAKE is not a stored result
        return {"status": "RETAKE", "reason": analysis["reason"], "quality": analysis.get("quality")}

    test_id = uuid.uuid4().hex
    img_path = UPLOAD_DIR / f"{test_id}{ext}"
    img_path.write_bytes(photo_bytes)                    # original bytes, never edited
    ann_path = None
    if analysis.get("_annotated_jpeg"):
        ann_path = UPLOAD_DIR / f"{test_id}_annotated.jpg"
        ann_path.write_bytes(analysis["_annotated_jpeg"])

    fields = {
        "id": test_id, "operator_id": user["operator_id"], "device_id": (device_id or "unknown")[:80],
        "server_time_utc": _now(), "client_time": client_time, "gps": gps,
        "kit_type": kit_type, "kit_lot": kit_lot, "kit_expiry": expiry.isoformat(),
        "image_sha256": hashlib.sha256(photo_bytes).hexdigest(),   # exact uploaded bytes
        "result": analysis["result"], "match_score": analysis["match_score"],
        "colour_scores": analysis["colour_scores"], "chart_version": load_kits()["version"],
        "protocol_steps": {"control_done": True, "timer_seconds": int(timer_seconds), "reading_window_s": window},
        "card_calibrated": analysis["card_calibrated"], "kit_calibrated": bool(kit.get("calibrated")),
    }
    sk = load_signing_key()
    try:
        rec = db.insert_test_chained(lambda prev: make_record(fields, prev, sk), img_path, ann_path)
    except Exception:
        for p in (img_path, ann_path):
            if p: Path(p).unlink(missing_ok=True)
        raise
    return {"status": "OK", "record": rec, "quality": analysis["quality"]}


def _row_summary(r):
    rec = json.loads(r["record_json"])
    return {"id": r["id"], "server_time_utc": rec["server_time_utc"], "operator_id": rec["operator_id"],
            "result": rec["result"], "match_score": rec["match_score"], "kit_type": rec["kit_type"],
            "kit_lot": rec["kit_lot"], "record_hash": rec["record_hash"]}


def list_tests(q=None, result=None, date_from=None, date_to=None, operator=None, limit=200):
    sql, args = "SELECT * FROM tests WHERE 1=1", []
    if q:
        like = f"%{q.strip()}%"
        sql += " AND (id LIKE ? OR operator_id LIKE ? OR kit_lot LIKE ? OR kit_type LIKE ? OR record_hash LIKE ?)"
        args += [like] * 5
    if result:
        sql += " AND result=?"; args.append(result.upper())
    if date_from:
        sql += " AND substr(server_time_utc,1,10)>=?"; args.append(date_from)
    if date_to:
        sql += " AND substr(server_time_utc,1,10)<=?"; args.append(date_to)
    if operator:
        sql += " AND operator_id=?"; args.append(operator)
    sql += " ORDER BY seq DESC LIMIT ?"; args.append(min(int(limit), 500))
    c = db.connect(); rows = c.execute(sql, args).fetchall(); c.close()
    return [_row_summary(r) for r in rows]


def get_row(test_id):
    c = db.connect(); r = c.execute("SELECT * FROM tests WHERE id=?", (test_id,)).fetchone(); c.close()
    if not r:
        raise ServiceError(404, "Record not found")
    return r


def get_test(test_id):
    r = get_row(test_id)
    return json.loads(r["record_json"])


def verify_test(test_id):
    """Public. Recomputes hash + signature, checks the chain link, the index columns and the image."""
    r = get_row(test_id)
    checks = {}
    try:
        rec = json.loads(r["record_json"])
    except Exception:
        return {"id": test_id, "valid": False, "checks": {"record_readable": False}}
    vk = load_signing_key().verify_key
    checks["hash_and_signature"] = verify_record(rec, vk)
    c = db.connect()
    prev = c.execute("SELECT record_hash FROM tests WHERE seq<? ORDER BY seq DESC LIMIT 1", (r["seq"],)).fetchone()
    c.close()
    expected_prev = prev["record_hash"] if prev else GENESIS_HASH
    checks["chain_link"] = rec.get("prev_hash") == expected_prev
    checks["index_matches_record"] = all([
        r["record_hash"] == rec.get("record_hash"), r["prev_hash"] == rec.get("prev_hash"),
        r["result"] == rec.get("result"), r["operator_id"] == rec.get("operator_id"),
        r["server_time_utc"] == rec.get("server_time_utc")])
    try:
        checks["image_matches_hash"] = hashlib.sha256(Path(r["image_path"]).read_bytes()).hexdigest() == rec.get("image_sha256")
    except Exception:
        checks["image_matches_hash"] = False
    return {"id": test_id, "valid": all(checks.values()), "checks": checks,
            "public_key": public_key_hex(load_signing_key()),
            "summary": {k: rec.get(k) for k in ("server_time_utc", "operator_id", "result", "match_score",
                                                  "kit_type", "kit_lot", "record_hash", "prev_hash", "signature")}}


def verify_full_chain():
    c = db.connect(); rows = c.execute("SELECT * FROM tests ORDER BY seq").fetchall(); c.close()
    vk = load_signing_key().verify_key
    prev = GENESIS_HASH
    for i, r in enumerate(rows):
        try:
            rec = json.loads(r["record_json"])
        except Exception:
            return {"ok": False, "checked": i, "total": len(rows), "bad_id": r["id"], "reason": "unreadable record"}
        if rec.get("prev_hash") != prev or r["prev_hash"] != prev:
            return {"ok": False, "checked": i, "total": len(rows), "bad_id": r["id"], "reason": "chain link broken"}
        if not verify_record(rec, vk):
            return {"ok": False, "checked": i, "total": len(rows), "bad_id": r["id"], "reason": "hash/signature mismatch"}
        prev = rec["record_hash"]
    return {"ok": True, "checked": len(rows), "total": len(rows)}
