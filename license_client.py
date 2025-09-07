# license_client.py
import hashlib, json, os, platform, uuid
import requests

LICENSE_CACHE = os.path.join(os.path.expanduser("~"), ".gocbt_license.json")
SERVER_BASE = os.environ.get("GOCBT_SERVER", "https://YOUR-RENDER-APP.onrender.com")

def _get_machine_id() -> str:
    try:
        node = uuid.getnode()
    except Exception:
        node = 0
    salt = "gocbt-salt-v1"
    raw = f"{platform.system()}|{platform.machine()}|{platform.node()}|{node}|{salt}"
    return hashlib.sha256(raw.encode()).hexdigest()

def _save_cache(data: dict):
    try:
        with open(LICENSE_CACHE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass

def _load_cache() -> dict:
    try:
        with open(LICENSE_CACHE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def activate_with_reference(email: str, reference: str):
    mid = _get_machine_id()
    url = f"{SERVER_BASE}/api/license/activate"
    r = requests.post(url, json={
        "email": email, "reference": reference, "machine_id": mid
    }, timeout=25)
    j = r.json()
    if j.get("ok"):
        data = {
            "email": email,
            "license_key": j["license_key"],
            "activation_token": j["activation_token"],
            "machine_id": mid
        }
        _save_cache(data)
    return j

def check_activation() -> dict:
    data = _load_cache()
    req = {
        "license_key": data.get("license_key",""),
        "activation_token": data.get("activation_token",""),
        "machine_id": data.get("machine_id") or _get_machine_id()
    }
    if not all(req.values()):
        return {"ok": False, "reason": "not_activated"}

    url = f"{SERVER_BASE}/api/license/check"
    try:
        r = requests.post(url, json=req, timeout=20)
        return r.json()
    except Exception as e:
        return {"ok": False, "reason": f"net_error: {e}"}
