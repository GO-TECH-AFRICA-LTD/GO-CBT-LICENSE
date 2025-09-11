# main.py — hardened startup (logger, singleton activation dialog, centered splash, robust portal)
import sys, traceback, datetime, os, webbrowser
import tkinter as tk
from tkinter import messagebox
def _log(msg: str):
    try:
        with open("gocbt_crash.log", "a", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now()}] {msg}\n")
    except Exception:
        pass
def _excepthook(t, e, tb):
    try:
        with open("gocbt_crash.log", "a", encoding="utf-8") as f:
            f.write(f"\n=== {datetime.datetime.now()} ===\n")
            traceback.print_exception(t, e, tb, file=f)
    except Exception:
        pass
sys.excepthook = _excepthook
GOCBT_SAFE = os.environ.get("GOCBT_SAFE", "0") == "1"
PAY_URL = "https://paystack.shop/pay/hpv92fjpxf"
APP_TITLE = "GO CBT APP"
try:
    from student_portal import GO_CBT_App
except Exception as e:
    _log(f"student_portal import failed: {e!r}")
    GO_CBT_App = None
try:
    from splash_screen import SplashScreen, show_loading_intro
except Exception as e:
    _log(f"splash_screen import failed (using fallback): {e!r}")
    class SplashScreen(tk.Toplevel):
        def __init__(self, master, on_agree_callback=None):
            super().__init__(master)
            self.title(APP_TITLE + " — Welcome"); self.resizable(False, False)
            outer = tk.Frame(self, padx=18, pady=18); outer.pack(fill="both", expand=True)
            tk.Label(outer, text=APP_TITLE, font=("Segoe UI", 14, "bold")).pack(pady=(0, 6))
            tk.Label(outer, text="Welcome! Click Continue to proceed.").pack(pady=(0, 12))
            tk.Button(outer, text="Continue",
                      command=lambda: (self.destroy(), on_agree_callback() if on_agree_callback else None)).pack()
            self.update_idletasks()
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            w, h = max(self.winfo_reqwidth(), 360), max(self.winfo_reqheight(), 160)
            x, y = (sw - w)//2, (sh - h)//3
            self.geometry(f"{w}x{h}+{x}+{y}")
    def show_loading_intro(root, on_done, duration_ms=1200):
        root.after(max(200, int(duration_ms)), on_done)
try:
    from activation_dialog import ActivationDialog
except Exception as e:
    _log(f"activation_dialog import delayed: {e!r}")
    ActivationDialog = None
def _open_buy():
    try: import webbrowser; webbrowser.open(PAY_URL)
    except Exception: pass
def _safe_check_activation():
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
def _center_window(win, w=None, h=None):
    try:
        win.update_idletasks()
        if w is None or h is None:
            w = w or win.winfo_reqwidth()
            h = h or win.winfo_reqheight()
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        x, y = max(0, (sw - w)//2), max(0, (sh - h)//3)
        win.geometry(f"{w}x{h}+{x}+{y}")
    except Exception: pass
def _ensure_activation(root, on_ready):
    if GOCBT_SAFE:
        _log("SAFE MODE: skipping activation"); on_ready(); return
    if getattr(root, "_license_dialog_open", False):
        _log("Activation dialog already open; skipping duplicate"); return
    res = _safe_check_activation()
    if res.get("ok"):
        _log("Activation OK"); on_ready(); return
    try:
        root.deiconify(); root.lift(); root.attributes("-topmost", True)
        root.after(150, lambda: root.attributes("-topmost", False)); root.focus_force()
    except Exception: pass
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
                dlg.update_idletasks(); dlg.lift(); dlg.attributes("-topmost", True); dlg.focus_force(); dlg.grab_set()
                for delay in (150, 300, 600, 900):
                    dlg.after(delay, lambda w=dlg: (w.lift(), w.attributes("-topmost", True), w.focus_force()))
                dlg.after(1100, lambda w=dlg: w.attributes("-topmost", False))
                try: dlg.bell()
                except Exception: pass
            except Exception: pass
            _log("ActivationDialog shown"); return
        except Exception as e:
            _log(f"ActivationDialog creation error: {e!r}")
    try:
        messagebox.showerror("Activation required",
            "Your GO CBT APP license could not be verified and the activation dialog failed to open.\n\n"
            "Click OK to visit the purchase/activation page.")
    except Exception: pass
    _open_buy(); _log("Soft-gate used (continuing without activation)"); on_ready()
def start_portal(root):
    _log("start_portal()")
    if GO_CBT_App is None:
        frm = tk.Frame(root); frm.pack(fill="both", expand=True)
        tk.Label(frm, text=APP_TITLE, font=("Segoe UI", 16, "bold")).pack(pady=12)
        tk.Label(frm, text="Portal module missing. Please check installation.").pack()
        return
    try:
        try:
            app = GO_CBT_App(root, title=APP_TITLE)
        except TypeError:
            app = GO_CBT_App(root); 
            try: root.title(APP_TITLE)
            except Exception: pass
    except Exception as e:
        _log(f"GO_CBT_App failed to start: {e!r}")
        frm = tk.Frame(root); frm.pack(fill="both", expand=True)
        tk.Label(frm, text=APP_TITLE, font=("Segoe UI", 16, "bold")).pack(pady=12)
        tk.Label(frm, text="An error occurred while starting the portal.").pack(pady=6)
        return
    try: _center_window(root, 960, 640)
    except Exception: pass
def start_app():
    root = tk.Tk(); root.title(APP_TITLE); root.geometry("900x700")
    try: root.withdraw()
    except Exception: pass
    def __start_splash():
        _log("__start_splash()"); root.deiconify()
        def proceed_callback():
            show_loading_intro(root, on_done=lambda: start_portal(root), duration_ms=1200)
        try:
            splash = SplashScreen(root, on_agree_callback=proceed_callback)
            try:
                splash.lift(); splash.focus_force()
                splash.attributes("-topmost", True)
                splash.after(150, lambda: splash.attributes("-topmost", False))
            except Exception: pass
            try: splash.grab_set()
            except Exception: pass
        except Exception as e:
            _log(f"Splash fallback used: {e!r}")
            show_loading_intro(root, on_done=lambda: start_portal(root), duration_ms=800)
    _ensure_activation(root, on_ready=__start_splash); root.mainloop()
if __name__ == "__main__": start_app()
