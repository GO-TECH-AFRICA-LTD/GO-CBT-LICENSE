# license_client.py — robust HTTPS with retries + clear errors
import os, json, platform, hashlib, requests, pathlib, time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

SERVER = os.environ.get("GOCBT_SERVER", "https://go-cbt-license.onrender.com").rstrip("/")
TIMEOUT = (6, 15)  # (connect, read)
STATE_FILE = "license_state.json"

def _machine_id() -> str:
    basis = f"{platform.node()}|{platform.system()}|{platform.machine()}|{platform.processor()}"
    return hashlib.sha256(basis.encode("utf-8", errors="ignore")).hexdigest()

def _state_path() -> str:
    return str(pathlib.Path(STATE_FILE).resolve())

def _load_state() -> dict:
    try:
        with open(_state_path(), "r", encoding="utf-8") as f:
            j = json.load(f)
            return j if isinstance(j, dict) else {}
    except Exception:
        return {}

def _save_state(license_key: str, activation_token: str):
    data = {"license_key": license_key, "activation_token": activation_token, "machine_id": _machine_id()}
    try:
        with open(_state_path(), "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass

def _session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=4,
        connect=4,
        read=4,
        backoff_factor=0.8,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "POST"]),
        raise_on_status=False,
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    # Respect HTTPS_PROXY/HTTP_PROXY from environment automatically
    return s

def _health_check(s: requests.Session) -> tuple[bool, str]:
    url = f"{SERVER}/healthz"
    try:
        r = s.get(url, timeout=10)
        return (r.ok, f"{r.status_code}")
    except Exception as e:
        return (False, str(e))

def activate_with_reference(email: str, reference: str) -> dict:
    """
    POST /api/license/activate {email, reference, machine_id}
    On success: saves {license_key, activation_token} locally.
    """
    s = _session()
    url = f"{SERVER}/api/license/activate"
    payload = {"email": email, "reference": reference, "machine_id": _machine_id()}
    try:
        r = s.post(url, json=payload, timeout=TIMEOUT)
        if r.status_code == 404:
            ok, info = _health_check(s)
            return {"ok": False, "error": f"activate 404 ({url}). healthz ok={ok} info={info}"}
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict) and data.get("ok") and data.get("license_key") and data.get("activation_token"):
            _save_state(data["license_key"], data["activation_token"])
        return data if isinstance(data, dict) else {"ok": False, "error": f"bad response: {data!r}"}
    except requests.exceptions.SSLError as e:
        return {"ok": False, "error": f"SSL error: {e}. If behind corporate proxy, set HTTPS_PROXY."}
    except requests.exceptions.ProxyError as e:
        return {"ok": False, "error": f"Proxy error: {e}. Check HTTPS_PROXY/HTTP_PROXY environment variables."}
    except requests.exceptions.ConnectTimeout:
        return {"ok": False, "error": "Connection timed out to server (port 443). Check network/AV/firewall."}
    except requests.exceptions.ConnectionError as e:
        ok, info = _health_check(s)
        return {"ok": False, "error": f"Connection error: {e}. healthz ok={ok} info={info}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def check_activation() -> dict:
    """
    POST /api/license/check {license_key, machine_id, activation_token}
    """
    st = _load_state()
    lic = st.get("license_key")
    tok = st.get("activation_token")
    mid = st.get("machine_id") or _machine_id()
    if not (lic and tok and mid):
        return {"ok": False, "error": "not_activated"}

    s = _session()
    url = f"{SERVER}/api/license/check"
    payload = {"license_key": lic, "machine_id": mid, "activation_token": tok}
    try:
        r = s.post(url, json=payload, timeout=TIMEOUT)
        if r.status_code == 404:
            ok, info = _health_check(s)
            return {"ok": False, "error": f"check 404 ({url}). healthz ok={ok} info={info}"}
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, dict) else {"ok": False, "error": f"bad response: {data!r}"}
    except requests.exceptions.SSLError as e:
        return {"ok": False, "error": f"SSL error: {e}. If behind corporate proxy, set HTTPS_PROXY."}
    except requests.exceptions.ProxyError as e:
        return {"ok": False, "error": f"Proxy error: {e}. Check HTTPS_PROXY/HTTP_PROXY environment variables."}
    except requests.exceptions.ConnectTimeout:
        return {"ok": False, "error": "Connection timed out to server (port 443). Check network/AV/firewall."}
    except requests.exceptions.ConnectionError as e:
        ok, info = _health_check(s)
        return {"ok": False, "error": f"Connection error: {e}. healthz ok={ok} info={info}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
