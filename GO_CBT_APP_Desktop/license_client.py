# license_client.py — minimal, stable, no duplicates
import os, platform, hashlib, requests
SERVER = os.environ.get("GOCBT_SERVER", "https://go-cbt-license.onrender.com")
TIMEOUT = (6, 10)
def _pc_fingerprint() -> str:
    basis = f"{platform.node()}|{platform.system()}|{platform.machine()}|{platform.processor()}"
    return hashlib.sha256(basis.encode("utf-8", errors="ignore")).hexdigest()
def activate_with_reference(email: str, reference: str) -> dict:
    url = f"{SERVER.rstrip('/')}/api/activate"
    payload = {"email": email, "reference": reference, "fingerprint": _pc_fingerprint()}
    try:
        r = requests.post(url, json=payload, timeout=TIMEOUT); r.raise_for_status(); data = r.json()
        return data if isinstance(data, dict) else {"ok": False, "error": f"bad response: {data!r}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
def check_activation() -> dict:
    url = f"{SERVER.rstrip('/')}/api/check"
    try:
        r = requests.get(url, params={"fingerprint": _pc_fingerprint()}, timeout=TIMEOUT); r.raise_for_status(); data = r.json()
        return data if isinstance(data, dict) else {"ok": False, "error": f"bad response: {data!r}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
