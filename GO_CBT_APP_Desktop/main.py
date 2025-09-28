# main.py — GO CBT APP startup (final)
# - Robust activation (singleton dialog, focus/topmost nudges, SAFE/force toggles)
# - Instructions splash → logo loading overlay → portal
# - Explicit first-render + auto-pack + watchdog (prevents blank window)
# - Compact log with auto-rotation

import os, sys, datetime, traceback, webbrowser
import tkinter as tk
from tkinter import messagebox

APP_TITLE = "GO CBT APP"
PAY_URL = "https://paystack.shop/pay/hpv92fjpxf"

# Env toggles
GOCBT_SAFE          = os.environ.get("GOCBT_SAFE", "0") == "1"        # skip activation
GOCBT_SKIP_SPLASH   = os.environ.get("GOCBT_SKIP_SPLASH", "0") == "1" # go straight to portal (dev)
GOCBT_FORCE_DIALOG  = os.environ.get("GOCBT_FORCE_DIALOG", "0") == "1" # force activation for testing

# ------------------------------- logging -------------------------------------
def _log(msg: str) -> None:
    path = "gocbt_crash.log"
    try:
        if os.path.exists(path) and os.path.getsize(path) > 200_000:
            # rotate
            try:
                os.replace(path, "gocbt_crash.prev.log")
            except Exception:
                pass
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now()}] {msg}\n")
    except Exception:
        pass

def _excepthook(exc_type, exc, tb):
    try:
        with open("gocbt_crash.log", "a", encoding="utf-8") as f:
            f.write("\n=== UNCAUGHT EXCEPTION ===\n")
            traceback.print_exception(exc_type, exc, tb, file=f)
            f.write("=== END EXCEPTION ===\n")
    except Exception:
        pass
    traceback.print_exception(exc_type, exc, tb, file=sys.stderr)

sys.excepthook = _excepthook

# ------------------------------ tiny helpers ---------------------------------
def _center_window(win: tk.Tk | tk.Toplevel, w: int = None, h: int = None) -> None:
    try:
        win.update_idletasks()
        if w is None or h is None:
            w = w or win.winfo_reqwidth()
            h = h or win.winfo_reqheight()
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        x, y = max(0, (sw - w) // 2), max(0, (sh - h) // 3)
        win.geometry(f"{max(320, w)}x{max(240, h)}+{x}+{y}")
    except Exception as e:
        _log(f"_center_window failed: {e!r}")

def _set_icon_if_available(win: tk.Tk | tk.Toplevel):
    try:
        from path_utils import find_app_icon
        icon = find_app_icon()
        if icon:
            try:
                win.iconbitmap(icon)
            except Exception:
                pass
    except Exception as e:
        _log(f"set_icon failed: {e!r}")

def _raise_to_front(win: tk.Tk | tk.Toplevel):
    try:
        win.deiconify(); win.lift()
        win.attributes("-topmost", True)
        win.after(220, lambda: win.attributes("-topmost", False))
        try:
            win.focus_force()
        except Exception:
            pass
    except Exception:
        pass

def _open_buy():
    try:
        webbrowser.open(PAY_URL)
    except Exception:
        pass

# ------------------------------ optional imports -----------------------------
try:
    from splash_screen import SplashScreen, show_loading_intro
except Exception as e:
    _log(f"splash_screen import failed (using fallback): {e!r}")

    class SplashScreen(tk.Toplevel):
        def __init__(self, master, on_agree_callback=None, title="GO CBT App — Welcome"):
            super().__init__(master)
            self.title(title); self.resizable(False, False)
            outer = tk.Frame(self, padx=18, pady=18); outer.pack(fill="both", expand=True)
            tk.Label(outer, text=APP_TITLE, font=("Segoe UI", 14, "bold")).pack(pady=(0, 6))
            tk.Label(outer, text="Welcome! Click Continue to proceed.").pack(pady=(0, 12))
            tk.Button(outer, text="Continue",
                      command=lambda: (self.destroy(), on_agree_callback() if on_agree_callback else None)).pack()
            _center_window(self, 520, 320)

    def show_loading_intro(root, on_done, duration_ms=1200):
        root.after(max(200, int(duration_ms)), on_done)

try:
    from activation_dialog import ActivationDialog
except Exception as e:
    _log(f"activation_dialog import delayed: {e!r}")
    ActivationDialog = None

# ------------------------------ portal wiring --------------------------------
GO_CBT_App = None

def _import_portal():
    """Lazy-import student_portal.GO_CBT_App so we can message failures cleanly."""
    global GO_CBT_App
    if GO_CBT_App is not None:
        return
    try:
        from student_portal import GO_CBT_App as _PortalClass
        GO_CBT_App = _PortalClass
        _log("student_portal.GO_CBT_App imported.")
    except Exception as e:
        GO_CBT_App = None
        _log(f"student_portal import failed: {e!r}")

def start_portal(root: tk.Tk):
    """Create the portal widget and ensure the first screen is rendered (no blank window)."""
    _log("starting portal …")
    _import_portal()

    if GO_CBT_App is None:
        frm = tk.Frame(root); frm.pack(fill="both", expand=True)
        tk.Label(frm, text=APP_TITLE, font=("Segoe UI", 16, "bold")).pack(pady=12)
        tk.Label(frm, text="Portal module missing. Please check installation.").pack()
        return

    # Instantiate defensively
    try:
        try:
            app = GO_CBT_App(root, title=APP_TITLE)
        except TypeError:
            app = GO_CBT_App(root)
            try:
                root.title(APP_TITLE)
            except Exception:
                pass
    except Exception as e:
        _log(f"GO_CBT_App failed to start: {e!r}")
        frm = tk.Frame(root); frm.pack(fill="both", expand=True)
        tk.Label(frm, text=APP_TITLE, font=("Segoe UI", 16, "bold")).pack(pady=12)
        tk.Label(frm, text="An error occurred while starting the portal.").pack(pady=6)
        return

    # Ensure the portal widget is actually placed in the window
    try:
        if isinstance(app, tk.Widget) and not app.winfo_manager():
            _log("auto-packing GO_CBT_App (was not managed)")
            app.pack(fill="both", expand=True)
    except Exception as e:
        _log(f"Auto-pack portal failed: {e!r}")

    # Explicitly render the first screen to avoid blank window
    try:
        for meth in (
            "show_login_page", "show_portal", "build_main_ui",
            "build_ui", "create_widgets", "render_portal", "setup_ui"
        ):
            if hasattr(app, meth):
                _log(f"rendering UI via {meth}()")
                getattr(app, meth)()
                break
        else:
            _log("Portal created but no known render method.")
    except Exception as e:
        _log(f"Rendering first screen failed: {e!r}")
        messagebox.showerror(APP_TITLE, f"Failed to render portal UI:\n{e!r}")
        return

    _center_window(root, 960, 640)

    # Watchdog: if nothing is visible after ~700ms, retry a secondary render or show fallback
    def _render_watchdog():
        try:
            kids = [w for w in root.winfo_children() if getattr(w, "winfo_manager", lambda: "")()]
            if not kids or all(getattr(w, "winfo_ismapped", lambda: False)() is False for w in kids):
                _log("watchdog: still blank → retrying a secondary render")
                for alt in ("show_portal", "build_main_ui", "build_ui", "create_widgets"):
                    if hasattr(app, alt):
                        try:
                            getattr(app, alt)(); _log(f"watchdog invoked {alt}()")
                            break
                        except Exception as ee:
                            _log(f"watchdog {alt}() failed: {ee!r}")
                root.after(350, lambda: _ensure_has_content_fallback(root))
        except Exception as ee:
            _log(f"watchdog error: {ee!r}")

    def _ensure_has_content_fallback(r: tk.Tk):
        try:
            kids = [w for w in r.winfo_children() if getattr(w, "winfo_manager", lambda: "")()]
            if kids:
                return
            frm = tk.Frame(r); frm.pack(fill="both", expand=True)
            tk.Label(frm, text=APP_TITLE, font=("Segoe UI", 16, "bold")).pack(pady=10)
            tk.Label(frm, text="Preparing the portal…", font=("Segoe UI", 11)).pack()
            tk.Button(frm, text="Try Again", command=lambda: start_portal(r)).pack(pady=10)
            _log("fallback UI shown to avoid blank window")
        except Exception as e:
            _log(f"fallback UI failed: {e!r}")

    root.after(700, _render_watchdog)
    try:
        root.lift(); root.focus_force()
        root.attributes("-topmost", True); root.after(200, lambda: root.attributes("-topmost", False))
    except Exception:
        pass

# ------------------------------ activation flow ------------------------------
def _safe_check_activation():
    """Call license_client.check_activation safely and normalize result."""
    try:
        from license_client import check_activation
    except Exception as e:
        _log(f"Import error: license_client.check_activation -> {e!r}")
        return {"ok": False, "error": "license client not available"}
    try:
        res = check_activation()
        if not isinstance(res, dict):
            return {"ok": False, "error": f"unexpected response: {res!r}"}
        return res
    except Exception as e:
        _log(f"check_activation raised: {e!r}")
        return {"ok": False, "error": str(e)}

def _ensure_activation(root: tk.Tk, on_ready):
    """Require activation; show dialog if not active. Supports SAFE and FORCE toggles."""
    if GOCBT_SAFE:
        _log("SAFE MODE: skipping activation")
        on_ready(); return

    if getattr(root, "_license_dialog_open", False):
        _log("Activation dialog already open; skipping duplicate")
        return

    res = _safe_check_activation()
    if GOCBT_FORCE_DIALOG:
        _log("GOCBT_FORCE_DIALOG=1 — forcing activation dialog for test")
        res = {"ok": False, "error": "forced_dialog"}

    if res.get("ok"):
        _log("Activation OK")
        on_ready(); return

    _raise_to_front(root)

    AD = None
    try:
        from activation_dialog import ActivationDialog as AD
    except Exception as e:
        _log(f"ActivationDialog import failed: {e!r}")
        if 'ActivationDialog' in globals() and callable(globals()['ActivationDialog']):
            AD = globals()['ActivationDialog']

    if AD is not None:
        try:
            dlg = AD(root, on_activated=on_ready)
            root._license_dialog_open = True
            dlg.bind("<Destroy>", lambda e: setattr(root, "_license_dialog_open", False))

            try:
                dlg.update_idletasks()
                _center_window(dlg, 640, 400)
                dlg.lift(); dlg.attributes("-topmost", True); dlg.focus_force(); dlg.grab_set()
                for delay in (150, 300, 600, 900):
                    dlg.after(delay, lambda w=dlg: (w.lift(), w.attributes("-topmost", True), w.focus_force()))
                dlg.after(1100, lambda w=dlg: w.attributes("-topmost", False))
                try: dlg.bell()
                except Exception: pass
            except Exception:
                pass

            _log("ActivationDialog shown")
            return
        except Exception as e:
            _log(f"ActivationDialog creation error: {e!r}")

    try:
        messagebox.showerror(
            "Activation required",
            "Your GO CBT APP license could not be verified and the activation dialog failed to open.\n\n"
            "Click OK to visit the purchase/activation page."
        )
    except Exception:
        pass
    _open_buy()
    _log("Soft-gate used (continuing without activation)")
    on_ready()

# ------------------------------ splash + launch ------------------------------
def _run_splash_then_portal(root: tk.Tk):
    """
    Show the instructions splash, then the loading overlay, then launch the portal.
    Includes a watchdog that falls back to the loading overlay if the splash
    does not become visible quickly (prevents empty window).
    """
    if GOCBT_SKIP_SPLASH:
        _log("GOCBT_SKIP_SPLASH=1 — skipping splash, going straight to portal")
        start_portal(root)
        return

    _log("showing splash …")

    def _fallback_to_loader(reason: str):
        _log(f"splash not visible → fallback to loader ({reason})")
        try:
            show_loading_intro(root, on_done=lambda: start_portal(root), duration_ms=3000)
        except Exception as ee:
            _log(f"show_loading_intro failed: {ee!r}")
            start_portal(root)

    try:
        splash = SplashScreen(
            root,
            on_agree_callback=lambda: _after_splash(root),
            title="GO CBT App — Instructions"
        )
    except Exception as e:
        _log(f"splash init failed: {e!r}")
        _fallback_to_loader("init-exception")
        return

    # Try very hard to make the splash visible and focused
    try:
        _set_icon_if_available(splash)
        _center_window(splash, 580, 430)

        # Ensure it actually maps
        try:
            splash.deiconify()
        except Exception:
            pass
        splash.update_idletasks()

        try:
            splash.transient(root)
            splash.grab_set()
        except Exception:
            pass

        try:
            splash.lift()
            splash.focus_force()
            splash.attributes("-topmost", True)
            splash.after(220, lambda: splash.attributes("-topmost", False))
        except Exception:
            pass
    except Exception as e:
        _log(f"splash show sequence failed: {e!r}")
        _fallback_to_loader("show-sequence-exception")
        return

    # Watchdog: if the splash is not visible within 900ms, fallback to loader
    def _watch_splash_visibility():
        try:
            if not splash.winfo_exists():
                _fallback_to_loader("destroyed")
                return
            mapped = False
            try:
                mapped = bool(splash.winfo_ismapped())
            except Exception:
                mapped = False
            if not mapped:
                _fallback_to_loader("not-mapped")
                try:
                    splash.destroy()
                except Exception:
                    pass
        except Exception as ee:
            _log(f"splash watchdog error: {ee!r}")
            _fallback_to_loader("watchdog-exception")

    # Some GPUs/remote desktops need a bit longer to map; check twice
    root.after(600, _watch_splash_visibility)
    root.after(1200, _watch_splash_visibility)

def _after_splash(root: tk.Tk):
    _log("splash accepted → launching portal")
    try:
        # This displays the centered 420x280 logo overlay for ~3s (implemented inside splash_screen.py)
        show_loading_intro(root, on_done=lambda: start_portal(root), duration_ms=3000)
    except Exception:
        start_portal(root)

# --------------------------------- entry -------------------------------------
def start_app():
    _log("start_app()")
    root = tk.Tk()
    _set_icon_if_available(root)
    root.withdraw()
    root.title(APP_TITLE)
    _center_window(root, 980, 660)
    root.deiconify()
    _raise_to_front(root)

    # Chain: activation -> splash -> loading overlay -> portal
    _ensure_activation(root, on_ready=lambda: _run_splash_then_portal(root))
    root.mainloop()

if __name__ == "__main__":
    start_app()
