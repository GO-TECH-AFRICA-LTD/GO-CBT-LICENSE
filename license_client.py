# license_client.py — align with server: /api/license/activate + /api/license/check
import os, json, platform, hashlib, requests, pathlib

SERVER = os.environ.get("GOCBT_SERVER", "https://go-cbt-license.onrender.com").rstrip("/")
TIMEOUT = (6, 12)  # (connect, read)
STATE_FILE = "license_state.json"  # saved alongside the EXE/py

def _machine_id() -> str:
    basis = f"{platform.node()}|{platform.system()}|{platform.machine()}|{platform.processor()}"
    return hashlib.sha256(basis.encode("utf-8", errors="ignore")).hexdigest()

def _state_path() -> str:
    # keep it simple: local folder; if you prefer %APPDATA%, adjust here
    return str(pathlib.Path(STATE_FILE).resolve())

def _load_state() -> dict:
    p = _state_path()
    try:
        with open(p, "r", encoding="utf-8") as f:
            j = json.load(f)
            return j if isinstance(j, dict) else {}
    except Exception:
        return {}

def _save_state(license_key: str, activation_token: str):
    data = {
        "license_key": license_key,
        "activation_token": activation_token,
        "machine_id": _machine_id(),
    }
    try:
        with open(_state_path(), "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass

def activate_with_reference(email: str, reference: str) -> dict:
    """
    POSTS to /api/license/activate with {email, reference, machine_id}.
    On success, saves {license_key, activation_token, machine_id} locally.
    Returns {ok: bool, ...}
    """
    url = f"{SERVER}/api/license/activate"
    payload = {"email": email, "reference": reference, "machine_id": _machine_id()}
    try:
        r = requests.post(url, json=payload, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict) and data.get("ok") and data.get("license_key") and data.get("activation_token"):
            _save_state(data["license_key"], data["activation_token"])
        return data if isinstance(data, dict) else {"ok": False, "error": f"bad response: {data!r}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def check_activation() -> dict:
    """
    POSTS to /api/license/check with saved {license_key, machine_id, activation_token}.
    Returns {ok: bool, ...}
    """
    st = _load_state()
    lic = st.get("license_key")
    tok = st.get("activation_token")
    mid = st.get("machine_id") or _machine_id()
    if not (lic and tok and mid):
        return {"ok": False, "error": "not_activated"}

    url = f"{SERVER}/api/license/check"
    payload = {"license_key": lic, "machine_id": mid, "activation_token": tok}
    try:
        r = requests.post(url, json=payload, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, dict) else {"ok": False, "error": f"bad response: {data!r}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
