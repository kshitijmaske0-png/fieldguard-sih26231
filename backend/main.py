"""FieldGuard API + static frontend.   Run:  uvicorn backend.main:app --host 0.0.0.0 --port 8000"""
import json, time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from . import db, service
from .config import FRONTEND_DIR, ROOT, MAX_UPLOAD_BYTES, jwt_secret, load_kits
from .records import load_signing_key, public_key_hex
from .report import build_pdf
from .service import ServiceError


@asynccontextmanager
async def lifespan(app):
    db.init_db(); db.seed_users(); load_signing_key()
    yield


app = FastAPI(title="FieldGuard", lifespan=lifespan)
_fails = {}   # username -> [timestamps]   (prototype-grade login throttle)


@app.exception_handler(ServiceError)
async def _service_error(_, e: ServiceError):
    return Response(json.dumps({"detail": e.message}), status_code=e.status, media_type="application/json")


def current_user(request: Request):
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(401, "Login required")
    try:
        payload = jwt.decode(auth[7:], jwt_secret(), algorithms=["HS256"])
    except Exception:
        raise HTTPException(401, "Session expired, please log in again")
    u = db.get_user(payload["sub"])
    if not u:
        raise HTTPException(401, "Unknown user")
    return u


@app.post("/api/auth/login")
def login(body: dict):
    name, pw = str(body.get("username", "")).strip(), str(body.get("password", ""))
    now = time.time()
    recent = [t for t in _fails.get(name, []) if now - t < 300]
    if len(recent) >= 5:
        raise HTTPException(429, "Too many attempts, wait a few minutes")
    u = db.get_user(name)
    if not u or not db.check_password(pw, u["salt"], u["pw_hash"]):
        _fails[name] = recent + [now]
        raise HTTPException(401, "Wrong username or password")
    _fails.pop(name, None)
    exp = datetime.now(timezone.utc) + timedelta(hours=12)
    token = jwt.encode({"sub": u["username"], "exp": exp}, jwt_secret(), algorithm="HS256")
    return {"token": token, "operator_id": u["operator_id"], "name": u["name"]}


@app.get("/api/me")
def me(user=Depends(current_user)):
    return {"operator_id": user["operator_id"], "name": user["name"]}


@app.get("/api/kits")
def kits(user=Depends(current_user)):
    k = load_kits()
    return {"version": k["version"], "kits": [
        {"id": i, "label": v["label"], "reading_window_s": v["reading_window_s"], "calibrated": v.get("calibrated", False)}
        for i, v in k["kits"].items()]}


@app.post("/api/tests")
async def create_test(photo: UploadFile = File(...), kit_type: str = Form(...), kit_lot: str = Form(...),
                      kit_expiry: str = Form(...), control_done: bool = Form(False), timer_seconds: int = Form(0),
                      gps: str = Form(""), client_time: str = Form(""), device_id: str = Form("unknown"),
                      user=Depends(current_user)):
    data = await photo.read(MAX_UPLOAD_BYTES + 1)
    g = None
    if gps:
        try:
            j = json.loads(gps); g = {"lat": float(j["lat"]), "lng": float(j["lng"]), "accuracy": float(j.get("acc", j.get("accuracy", 0)))}
        except Exception:
            g = None
    return await run_in_threadpool(service.create_test, user, data, kit_type, kit_lot, kit_expiry, control_done,
                                   timer_seconds, g, client_time or None, device_id)


@app.get("/api/tests")
def list_tests(q: str = "", result: str = "", operator: str = "", date_from: str = "", date_to: str = "",
               user=Depends(current_user)):
    return service.list_tests(q or None, result or None, date_from or None, date_to or None, operator or None)


@app.get("/api/tests/{test_id}")
def get_test(test_id: str, user=Depends(current_user)):
    return service.get_test(test_id)


def _file(test_id, col):
    r = service.get_row(test_id)
    p = r[col]
    if not p or not Path(p).exists():
        raise HTTPException(404, "Image not found")
    return FileResponse(p)


@app.get("/api/tests/{test_id}/image")
def image(test_id: str, user=Depends(current_user)):
    return _file(test_id, "image_path")


@app.get("/api/tests/{test_id}/annotated")
def annotated(test_id: str, user=Depends(current_user)):
    return _file(test_id, "annotated_path")


@app.get("/api/verify-chain")
def verify_chain():
    return service.verify_full_chain()


@app.get("/api/pubkey")
def pubkey():
    return {"algorithm": "Ed25519", "public_key_hex": public_key_hex()}


@app.get("/api/verify/{test_id}")
def verify(test_id: str):                       # public: no login (QR code target)
    return service.verify_test(test_id)


@app.get("/api/tests/{test_id}/report.pdf")
def report(test_id: str, request: Request, user=Depends(current_user)):
    row = service.get_row(test_id)
    rec = json.loads(row["record_json"])
    v = service.verify_test(test_id)
    url = f"{str(request.base_url).rstrip('/')}/#/verify/{test_id}"
    pdf = build_pdf(rec, url, v["valid"], row["image_path"], row["annotated_path"])
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="fieldguard-{test_id[:8]}.pdf"'})


@app.get("/card.pdf")
def card():
    return FileResponse(ROOT / "assets" / "card.pdf", filename="fieldguard-reference-card.pdf")


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
