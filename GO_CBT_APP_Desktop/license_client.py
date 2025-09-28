# license_client.py — resilient licensing for GO CBT APP (final)
# - Public API (unchanged): check_activation(), activate(key, user=None, machine_id=None),
#   deactivate(), clear_state()
# - Robust HTTP: retries/backoff + env-tunable timeouts
# - TLS trust: REQUESTS_CA_BUNDLE preferred; fallback to assets/cacerts_merged.pem; else system CAs
# - Pre-warm /health (handles Render cold starts)
# - Offline OK when a valid local state exists (configurable via GOCBT_OFFLINE_OK)
# - Frozen-aware state file path (next to EXE)
# - Small CLI for quick checks: `python license_client.py check|activate|deactivate|clear`

from __future__ import annotations

import os
import sys
import json
import uuid
import hashlib
import platform
import socket
import datetime
from typing import Any, Dict, Optional

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    from requests.exceptions import SSLError, ReadTimeout, ConnectTimeout, ConnectionError as ReqConnErr
except Exception:
    requests = None  # type: ignore

# -------------------------- Configuration knobs --------------------------

SERVER = os.environ.get("GOCBT_SERVER", "https://go-cbt-license.onrender.com").rstrip("/")

# Timeouts (connect, read) — override via env without rebuild
CONNECT_TO = int(os.environ.get("GOCBT_CONNECT_TIMEOUT", "8"))
READ_TO    = int(os.environ.get("GOCBT_READ_TIMEOUT", "45"))  # generous for first warm-up
TIMEOUT    = (CONNECT_TO, READ_TO)

# Retries / backoff
RETRIES        = int(os.environ.get("GOCBT_RETRIES", "5"))
BACKOFF_FACTOR = float(os.environ.get("GOCBT_BACKOFF", "1.2"))

# Accept local activation when offline?
OFFLINE_OK = os.environ.get("GOCBT_OFFLINE_OK", "1") == "1"

# TLS settings
CA_BUNDLE = os.environ.get("REQUESTS_CA_BUNDLE", "").strip()  # preferred, if set
INSECURE  = os.environ.get("GOCBT_INSECURE", "0") == "1"      # diagnostic only (avoid in prod)

# Files & logging
STATE_FILE = os.environ.get("GOCBT_STATE_FILE", "license_state.json")
LOG_FILE   = os.environ.get("GOCBT_LOG_FILE", "gocbt_crash.log")

APP_NAME   = "gocbt-desktop"  # product identifier sent to server


# ------------------------------- Utilities --------------------------------

def _log(msg: str) -> None:
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def _app_dir() -> str:
    return os.path.dirname(sys.executable) if _is_frozen() else os.path.dirname(os.path.abspath(__file__))


def _state_path() -> str:
    return os.path.join(_app_dir(), STATE_FILE)


def _load_state() -> Optional[Dict[str, Any]]:
    try:
        p = _state_path()
        if not os.path.exists(p):
            return None
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        _log(f"load_state failed: {e!r}")
        return None


def _save_state(data: Dict[str, Any]) -> bool:
    try:
        p = _state_path()
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, p)
        return True
    except Exception as e:
        _log(f"save_state failed: {e!r}")
        return False


def _clear_state_file() -> bool:
    try:
        p = _state_path()
        if os.path.exists(p):
            os.remove(p)
        return True
    except Exception as e:
        _log(f"clear_state_file failed: {e!r}")
        return False


def _machine_id() -> str:
    # Stable but anonymous machine fingerprint
    try:
        node = uuid.getnode()
        host = socket.gethostname()
        plat = f"{platform.system()}-{platform.release()}-{platform.machine()}"
        raw = f"{node}-{host}-{plat}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    except Exception:
        return uuid.uuid4().hex[:32]


def _now_iso() -> str:
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _assets_ca_default() -> Optional[str]:
    """
    If REQUESTS_CA_BUNDLE isn't set, we auto-use a bundled CA if present:
        <AppFolder>/assets/cacerts_merged.pem
    Works for both frozen EXE and source runs.
    """
    try:
        base = _app_dir()
        p = os.path.join(base, "assets", "cacerts_merged.pem")
        return p if os.path.exists(p) else None
    except Exception:
        return None


def _verify_param():
    """
    Decide what to pass to requests' 'verify' parameter:
      1) INSECURE=1  -> False (disable TLS verify)  [diagnostic only]
      2) REQUESTS_CA_BUNDLE -> that file (if exists)
      3) bundled assets/cacerts_merged.pem -> path (if exists)
      4) True (system/Certifi CAs)
    """
    if INSECURE:
        _log("WARNING: GOCBT_INSECURE=1 — TLS verification disabled (diagnostic only).")
        return False

    if CA_BUNDLE:
        if os.path.exists(CA_BUNDLE):
            _log(f"Using REQUESTS_CA_BUNDLE: {CA_BUNDLE}")
            return CA_BUNDLE
        else:
            _log(f"REQUESTS_CA_BUNDLE set but file not found: {CA_BUNDLE}. Falling back.")

    bundled = _assets_ca_default()
    if bundled:
        _log(f"Using bundled CA: {bundled}")
        return bundled

    return True


def _session() -> "requests.Session":
    if requests is None:
        raise RuntimeError("requests not available")

    s = requests.Session()
    retry = Retry(
        total=RETRIES,
        connect=RETRIES,
        read=RETRIES,
        backoff_factor=BACKOFF_FACTOR,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "POST"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=8, pool_maxsize=8)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


def _prewarm(s: "requests.Session") -> None:
    # Best-effort warm-up; ignore errors.
    try:
        s.get(f"{SERVER}/health", timeout=(5, 20), verify=_verify_param())
    except Exception:
        pass


def _normalize_error(prefix: str, exc: Exception) -> str:
    if isinstance(exc, (ReadTimeout, ConnectTimeout)):
        return f"{prefix}: Connection timed out. Please check your network and try again."
    if isinstance(exc, SSLError):
        return f"{prefix}: TLS/Certificate error. If on a corporate network, ensure your CA bundle is set."
    if isinstance(exc, ReqConnErr):
        return f"{prefix}: Connection error: {exc!s}"
    return f"{prefix}: {exc!s}"


# ------------------------------- Public API --------------------------------

def check_activation() -> Dict[str, Any]:
    """
    Returns:
      { "ok": True,  "product": "...", "licensed_to": "...", "machine_id": "...", ... }
      { "ok": False, "error": "..." }
    Behavior:
      - If local state exists and OFFLINE_OK=1, returns ok=True without contacting server.
      - Otherwise tries online /api/license/check (with pre-warm).
    """
    state = _load_state()
    if state and OFFLINE_OK:
        return {
            "ok": True,
            "product": state.get("product", APP_NAME),
            "licensed_to": state.get("licensed_to"),
            "machine_id": state.get("machine_id"),
            "activated_at": state.get("activated_at"),
            "offline": True,
        }

    if requests is None:
        return {"ok": False, "error": "requests module not available"}

    try:
        s = _session()
        _prewarm(s)
        payload = {"machine_id": _machine_id(), "hostname": socket.gethostname()}
        resp = s.post(f"{SERVER}/api/license/check", json=payload, timeout=TIMEOUT, verify=_verify_param())
        if resp.status_code >= 400:
            # Fallback to offline if allowed and we have a state
            if state and OFFLINE_OK:
                return {
                    "ok": True,
                    "product": state.get("product", APP_NAME),
                    "licensed_to": state.get("licensed_to"),
                    "machine_id": state.get("machine_id"),
                    "activated_at": state.get("activated_at"),
                    "offline": True,
                    "note": f"server_check_failed:{resp.status_code}",
                }
            return {"ok": False, "error": f"License check failed ({resp.status_code})."}

        data = resp.json() if resp.content else {}

        if data.get("ok"):
            merged = {
                "ok": True,
                "product": data.get("product", state.get("product") if state else APP_NAME),
                "licensed_to": data.get("licensed_to", state.get("licensed_to") if state else None),
                "machine_id": data.get("machine_id", _machine_id()),
                "activated_at": data.get("activated_at", state.get("activated_at") if state else _now_iso()),
                "offline": False,
            }
            # Persist lean state
            _save_state({
                "product": merged["product"],
                "licensed_to": merged["licensed_to"],
                "machine_id": merged["machine_id"],
                "activated_at": merged["activated_at"],
            })
            return merged

        return {"ok": False, "error": data.get("error") or "License not active."}

    except Exception as e:
        msg = _normalize_error("License check error", e)
        _log(msg)
        if state and OFFLINE_OK:
            return {
                "ok": True,
                "product": state.get("product", APP_NAME),
                "licensed_to": state.get("licensed_to"),
                "machine_id": state.get("machine_id"),
                "activated_at": state.get("activated_at"),
                "offline": True,
                "note": "network_error_offline_ok",
            }
        return {"ok": False, "error": msg}


def activate(license_key: str, user: Optional[str] = None, machine_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Activate this machine with the given license key.
    Returns { "ok": True, ... } or { "ok": False, "error": "..." }.
    """
    if not license_key or not isinstance(license_key, str):
        return {"ok": False, "error": "License key is required."}
    if requests is None:
        return {"ok": False, "error": "requests module not available"}

    mid = machine_id or _machine_id()
    payload = {
        "license_key": license_key.strip(),
        "machine_id": mid,
        "user": (user or "").strip() or None,
        "hostname": socket.gethostname(),
        "platform": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "app": APP_NAME,
    }

    try:
        s = _session()
        _prewarm(s)
        resp = s.post(f"{SERVER}/api/license/activate", json=payload, timeout=TIMEOUT, verify=_verify_param())
        if resp.status_code >= 400:
            try:
                data = resp.json()
                msg = data.get("error") or f"Activation failed ({resp.status_code})."
            except Exception:
                msg = f"Activation failed ({resp.status_code})."
            return {"ok": False, "error": msg}

        data = resp.json() if resp.content else {}
        if not data or not data.get("ok"):
            return {"ok": False, "error": data.get("error") or "Activation failed: unexpected server response."}

        state = {
            "product": data.get("product", APP_NAME),
            "licensed_to": data.get("licensed_to") or user,
            "machine_id": mid,
            "activated_at": data.get("activated_at") or _now_iso(),
            "license_hint": f"****{license_key[-4:]}" if len(license_key) >= 4 else None,
        }
        _save_state(state)
        return {"ok": True, **state}

    except Exception as e:
        msg = _normalize_error("Activation failed", e)
        _log(msg)
        return {"ok": False, "error": msg}

def activate_with_reference(license_key: str,
                            email: Optional[str] = None,
                            user: Optional[str] = None,
                            reference: Optional[str] = None,
                            machine_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Back-compat wrapper for UIs that pass a 'reference' (receipt/ref) and possibly 'user'.
    Server requires: email, reference, machine_id.
      - We map user -> email when email is not provided.
      - We always include 'email' and 'machine_id' in the payload.
    """
    if not license_key or not isinstance(license_key, str):
        return {"ok": False, "error": "License key is required."}
    if requests is None:
        return {"ok": False, "error": "requests module not available"}

    # Normalize inputs
    eml = (email or user or "").strip() or None
    ref = (reference or "").strip() or None
    mid = (machine_id or _machine_id())

    # Client-side guardrails (clearer error before hitting server)
    if not eml or not ref or not mid:
        missing = []
        if not eml: missing.append("email")
        if not ref: missing.append("reference")
        if not mid: missing.append("machine_id")
        return {"ok": False, "error": f"{', '.join(missing)} required"}

    payload = {
        "license_key": license_key.strip(),
        "email": eml,                 # <-- server expects 'email'
        "reference": ref,             # <-- server expects 'reference'
        "machine_id": mid,            # <-- explicitly include
        "user": (user or email or "").strip() or None,  # optional, for server bookkeeping
        "hostname": socket.gethostname(),
        "platform": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "app": APP_NAME,
    }

    try:
        s = _session()
        _prewarm(s)
        resp = s.post(f"{SERVER}/api/license/activate", json=payload, timeout=TIMEOUT, verify=_verify_param())
        if resp.status_code >= 400:
            try:
                data = resp.json()
                msg = data.get("error") or f"Activation failed ({resp.status_code})."
            except Exception:
                msg = f"Activation failed ({resp.status_code})."
            return {"ok": False, "error": msg}

        data = resp.json() if resp.content else {}
        if not data or not data.get("ok"):
            return {"ok": False, "error": data.get("error") or "Activation failed: unexpected server response."}

        state = {
            "product": data.get("product", APP_NAME),
            "licensed_to": data.get("licensed_to") or eml,
            "machine_id": mid,
            "activated_at": data.get("activated_at") or _now_iso(),
            "license_hint": f"****{license_key[-4:]}" if len(license_key) >= 4 else None,
        }
        _save_state(state)
        return {"ok": True, **state}

    except Exception as e:
        msg = _normalize_error("Activation failed", e)
        _log(msg)
        return {"ok": False, "error": msg}

def deactivate() -> Dict[str, Any]:
    """
    Best-effort server deactivation; always clears local state.
    """
    state = _load_state()
    if requests is None:
        _clear_state_file()
        return {"ok": False, "error": "requests not available; cleared local state only."}

    try:
        s = _session()
        _prewarm(s)
        payload = {
            "machine_id": (state or {}).get("machine_id") or _machine_id(),
            "hostname": socket.gethostname(),
        }
        try:
            resp = s.post(f"{SERVER}/api/license/deactivate", json=payload, timeout=TIMEOUT, verify=_verify_param())
            _clear_state_file()
            if resp.status_code >= 400:
                return {"ok": False, "error": f"Server responded {resp.status_code}; local state cleared."}
        except Exception as e:
            _clear_state_file()
            return {"ok": False, "error": _normalize_error("Deactivation error", e)}
        return {"ok": True}
    except Exception as e:
        _clear_state_file()
        return {"ok": False, "error": f"Unexpected error: {e!s}"}


def clear_state() -> Dict[str, Any]:
    ok = _clear_state_file()
    return {"ok": ok, "error": None if ok else "Failed to remove local state."}


# ------------------------------- CLI (optional quick tests) -----------------

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="GO CBT license client")
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("check", help="Check activation (offline OK if local state and OFFLINE_OK=1)")

    ac = sub.add_parser("activate", help="Activate this machine")
    ac.add_argument("--key", required=True, help="License key")
    ac.add_argument("--user", default=None, help="Licensed to (email/name)")
    ac.add_argument("--mid",  default=None, help="Override machine id (optional)")

    sub.add_parser("deactivate", help="Deactivate on server and clear local state")
    sub.add_parser("clear", help="Clear local state only")

    args = ap.parse_args()
    if args.cmd == "check":
        print(json.dumps(check_activation(), indent=2))
    elif args.cmd == "activate":
        print(json.dumps(activate(args.key, user=args.user, machine_id=args.mid), indent=2))
    elif args.cmd == "deactivate":
        print(json.dumps(deactivate(), indent=2))
    elif args.cmd == "clear":
        print(json.dumps(clear_state(), indent=2))
    else:
        ap.print_help()
