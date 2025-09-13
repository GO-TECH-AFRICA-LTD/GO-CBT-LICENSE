# license_client.py — robust, server-aligned, diagnostic-friendly
import os, json, platform, hashlib, requests, pathlib
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Server base URL (set via environment variable or fallback to Render URL)
SERVER = os.environ.get("GOCBT_SERVER", "https://go-cbt-license.onrender.com").rstrip("/")
TIMEOUT = (6, 15)  # (connect, read)
STATE_FILE = "license_state.json"

# DIAGNOSTIC toggle only: set GOCBT_INSECURE=1 to skip SSL verify (do not ship to clients)
INSECURE = os.environ.get("GOCBT_INSECURE", "0") == "1"

def _machine_id() -> str:
    """Generate a stable machine ID fingerprint."""
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

def _session() -> requests.Session:
    """Return a requests session with retry + proxy support."""
    s = requests.Session()
    retry = Retry(
        total=4,
        connect=4,
        read=4,
        backoff_factor=0.8,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "POST"]),
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    return s

def activate_with_reference(email: str, reference: str) -> dict:
    """
    Activate this machine using email + Paystack reference.
    Calls: POST /api/license/activate
    """
    url = f"{SERVER}/api/license/activate"
    payload = {"email": email, "reference": reference, "machine_id": _machine_id()}
    s = _session()
    try:
        r = s.post(url, json=payload, timeout=TIMEOUT, verify=not INSECURE)
        if r.status_code == 404:
            return {"ok": False, "error": f"404 at {url} — check server routes"}
        r.raise_for_status()
        data = r.json()
        if (
            isinstance(data, dict)
            and data.get("ok")
            and data.get("license_key")
            and data.get("activation_token")
        ):
            _save_state(data["license_key"], data["activation_token"])
        return data if isinstance(data, dict) else {"ok": False, "error": f"bad response: {data!r}"}
    except requests.exceptions.SSLError as e:
        return {
            "ok": False,
            "error": f"SSL error: {e}. If your network inspects SSL, set REQUESTS_CA_BUNDLE to company root PEM.",
        }
    except requests.exceptions.ProxyError as e:
        return {"ok": False, "error": f"Proxy error: {e}. Set HTTPS_PROXY/HTTP_PROXY env vars."}
    except requests.exceptions.ConnectTimeout:
        return {"ok": False, "error": "Connection timed out (port 443). Check firewall/AV or proxy."}
    except requests.exceptions.ConnectionError as e:
        return {"ok": False, "error": f"Connection error: {e}. Try diag script/net rules."}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def check_activation() -> dict:
    """
    Verify license validity on this machine.
    Calls: POST /api/license/check
    """
    st = _load_state()
    lic = st.get("license_key")
    tok = st.get("activation_token")
    mid = st.get("machine_id") or _machine_id()
    if not (lic and tok and mid):
        return {"ok": False, "error": "not_activated"}

    url = f"{SERVER}/api/license/check"
    payload = {"license_key": lic, "machine_id": mid, "activation_token": tok}
    s = _session()
    try:
        r = s.post(url, json=payload, timeout=TIMEOUT, verify=not INSECURE)
        if r.status_code == 404:
            return {"ok": False, "error": f"404 at {url} — check server routes"}
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, dict) else {"ok": False, "error": f"bad response: {data!r}"}
    except requests.exceptions.SSLError as e:
        return {
            "ok": False,
            "error": f"SSL error: {e}. If your network inspects SSL, set REQUESTS_CA_BUNDLE to company root PEM.",
        }
    except requests.exceptions.ProxyError as e:
        return {"ok": False, "error": f"Proxy error: {e}. Set HTTPS_PROXY/HTTP_PROXY env vars."}
    except requests.exceptions.ConnectTimeout:
        return {"ok": False, "error": "Connection timed out (port 443). Check firewall/AV or proxy."}
    except requests.exceptions.ConnectionError as e:
        return {"ok": False, "error": f"Connection error: {e}. Try diag script/net rules."}
    except Exception as e:
        return {"ok": False, "error": str(e)}
