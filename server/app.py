from flask import Flask, request, jsonify
from config import settings
from db import Base, engine, get_db
from models import License
from security import make_license_key, sign_token, unsign_token, verify_paystack_signature
from paystack import verify_transaction
from sqlalchemy.orm import Session
import os

app = Flask(__name__)
Base.metadata.create_all(bind=engine)

@app.get("/")
def root():
    return {"ok": True, "msg": "GO CBT license server running", "product": settings.PRODUCT_CODE}

@app.get("/healthz")
def healthz():
    return {"ok": True, "product": settings.PRODUCT_CODE}

@app.get("/debug/db")
def debug_db():
    url = os.environ.get("DATABASE_URL", "sqlite:///local.db" if settings.DATABASE_URL == "sqlite:///local.db" else "(set)" )
    if url and url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return {"DATABASE_URL": url}

@app.post("/paystack/webhook")
def paystack_webhook():
    body = request.get_data()
    sig = request.headers.get("x-paystack-signature", "")
    if not verify_paystack_signature(body, sig):
        return "invalid signature", 400
    return "ok", 200

@app.post("/api/license/activate")
def activate():
    j = request.get_json(force=True)
    email = (j.get("email") or "").strip().lower()
    reference = (j.get("reference") or "").strip()
    machine_id = (j.get("machine_id") or "").strip()
    if not (email and reference and machine_id):
        return jsonify({"ok": False, "error": "email, reference, machine_id required"}), 400

    v = verify_transaction(reference)
    if not v.get("status"):
        return jsonify({"ok": False, "error": "verification_failed"}), 400
    data = v.get("data") or {}
    if data.get("status") != "success":
        return jsonify({"ok": False, "error": "payment_not_successful"}), 400

    with next(get_db()) as db:  # type: Session
        lic = db.query(License).filter_by(paid_reference=reference).first()
        if not lic:
            key = make_license_key(email, reference, settings.PRODUCT_CODE)
            lic = License(
                email=email, license_key=key, product_code=settings.PRODUCT_CODE,
                paid_reference=reference, status="active", machine_id=machine_id
            )
            db.add(lic); db.commit(); db.refresh(lic)
        else:
            if lic.machine_id and lic.machine_id != machine_id:
                return jsonify({"ok": False, "error": "already_activated_on_another_pc"}), 403
            if not lic.machine_id:
                lic.machine_id = machine_id; db.commit()

        token = sign_token("{}|{}".format(lic.license_key, lic.machine_id))
        return jsonify({"ok": True, "license_key": lic.license_key, "activation_token": token})

@app.post("/api/license/check")
def check():
    j = request.get_json(force=True)
    license_key = (j.get("license_key") or "").strip()
    machine_id = (j.get("machine_id") or "").strip()
    token = (j.get("activation_token") or "").strip()
    if not (license_key and machine_id and token):
        return jsonify({"ok": False, "error": "missing_fields"}), 400

    raw = unsign_token(token)
    if not raw:
        return jsonify({"ok": False, "error": "bad_token"}), 401

    t_key, t_mid = raw.split("|") if "|" in raw else ("","" )
    if t_key != license_key or t_mid != machine_id:
        return jsonify({"ok": False, "error": "mismatch"}), 401

    with next(get_db()) as db:
        lic = db.query(License).filter_by(license_key=license_key).first()
        if not lic or lic.status != "active":
            return jsonify({"ok": False, "error": "invalid_license"}), 403
        if lic.machine_id != machine_id:
            return jsonify({"ok": False, "error": "already_activated_on_another_pc"}), 403
    return jsonify({"ok": True, "product": settings.PRODUCT_CODE})
