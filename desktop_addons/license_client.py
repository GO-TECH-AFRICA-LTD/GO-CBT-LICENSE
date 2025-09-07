import hashlib, json, os, platform, uuid, requests
LICENSE_CACHE = os.path.join(os.path.expanduser("~"), ".gocbt_license.json")
SERVER_BASE = os.environ.get("GOCBT_SERVER", "https://YOUR-RENDER-APP.onrender.com")

def _get_machine_id() -> str:
    try: node = uuid.getnode()
    except Exception: node = 0
    raw = f"{platform.system()}|{platform.machine()}|{platform.node()}|{node}|gocbt-salt-v1"
    return hashlib.sha256(raw.encode()).hexdigest()

def _save_cache(d):
    try:
        with open(LICENSE_CACHE,"w",encoding="utf-8") as f:
            json.dump(d,f)
    except: pass

def _load_cache():
    try:
        with open(LICENSE_CACHE,"r",encoding="utf-8") as f:
            return json.load(f)
    except: return {}

def activate_with_reference(email, reference):
    mid = _get_machine_id()
    r = requests.post(f"{SERVER_BASE}/api/license/activate",
                      json={"email": email,"reference": reference,"machine_id": mid}, timeout=25)
    j = r.json()
    if j.get("ok"):
        _save_cache({"email": email,"license_key": j["license_key"],
                     "activation_token": j["activation_token"],"machine_id": mid})
    return j

def check_activation():
    d = _load_cache()
    req = {"license_key": d.get("license_key",""),
           "activation_token": d.get("activation_token",""),
           "machine_id": d.get("machine_id") or _get_machine_id()}
    if not all(req.values()):
        return {"ok": False, "reason": "not_activated"}
    try:
        return requests.post(f"{SERVER_BASE}/api/license/check", json=req, timeout=20).json()
    except Exception as e:
        return {"ok": False, "reason": f"net_error: {e}"}
