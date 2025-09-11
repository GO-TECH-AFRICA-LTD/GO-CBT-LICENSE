# activation_dialog.py — classic layout (Activate / Buy License / Close) with auto-size
import tkinter as tk
from tkinter import messagebox
import datetime
from license_client import activate_with_reference
APP_NAME = "GO CBT APP"
PAY_URL = "https://paystack.shop/pay/hpv92fjpxf"
SUPPORT_PHONE = "08066713410"
LOGO_FILE = "gocbt_logo.png"
def _alog(msg: str):
    try:
        with open("gocbt_crash.log", "a", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now()}] [activation_dialog] {msg}\n")
    except Exception: pass
def _load_logo_scaled(path, max_w=320, max_h=160):
    try:
        from PIL import Image, ImageTk
        img = Image.open(path)
        try:
            from PIL.Image import Resampling
            img.thumbnail((max_w, max_h), Resampling.LANCZOS)
        except Exception:
            img.thumbnail((max_w, max_h))
        return ImageTk.PhotoImage(img)
    except Exception:
        try:
            ph = tk.PhotoImage(file=path)
            w, h = ph.width(), ph.height()
            if not w or not h: return None
            sub = int(max(w / max_w, h / max_h, 1.0) + 0.5)
            return ph.subsample(sub, sub) if sub > 1 else ph
        except Exception:
            return None
class ActivationDialog(tk.Toplevel):
    def __init__(self, master, buy_url: str = PAY_URL, on_activated=None):
        super().__init__(master)
        self.title(f"{APP_NAME} — Activation"); self.resizable(True, True)
        self.buy_url = buy_url; self.on_activated = on_activated
        outer = tk.Frame(self, padx=18, pady=18); outer.pack(fill="both", expand=True)
        self._logo_img = _load_logo_scaled(LOGO_FILE, 320, 160)
        if self._logo_img: tk.Label(outer, image=self._logo_img).pack(pady=(0, 8))
        tk.Label(outer, text=f"{APP_NAME} (1 PC License)", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 6))
        tk.Label(outer, text="Enter the email you paid with:").pack(anchor="w")
        self.email_var = tk.StringVar(); tk.Entry(outer, textvariable=self.email_var, width=42).pack(pady=(0, 8))
        tk.Label(outer, text="Enter your Paystack payment reference:").pack(anchor="w")
        self.ref_var = tk.StringVar(); tk.Entry(outer, textvariable=self.ref_var, width=42).pack(pady=(0, 12))
        tk.Label(outer, text="Note: License binds to this PC. For another PC, purchase another license.", fg="#444").pack(anchor="w", pady=(0, 10))
        tk.Frame(outer, height=1, bg="#dddddd").pack(fill="x", pady=(6, 10))
        btns = tk.Frame(outer); btns.pack(fill="x", pady=(0, 0))
        self.btn_activate = tk.Button(btns, text="Activate", width=12, command=self._do_activate)
        self.btn_buy = tk.Button(btns, text="Buy License", width=12, command=self._open_buy)
        self.btn_close = tk.Button(btns, text="Close", width=10, command=self._on_close)
        self.btn_activate.pack(side="left"); self.btn_buy.pack(side="left", padx=(8, 0)); self.btn_close.pack(side="right")
        tk.Label(outer, text=f"Support: {SUPPORT_PHONE}", fg="#666").pack(anchor="e", pady=(12, 0))
        self.protocol("WM_DELETE_WINDOW", self._on_close); self.after(0, self._post_init_focus)
    def _post_init_focus(self):
        try:
            self.update_idletasks()
            req_w = max(self.winfo_reqwidth(), 640); req_h = max(self.winfo_reqheight(), 480)
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            w = min(req_w, int(sw * 0.85)); h = min(req_h, int(sh * 0.85))
            x, y = max(0, (sw - w)//2), max(0, (sh - h)//3)
            self.geometry(f"{w}x{h}+{x}+{y}")
            self.lift(); self.attributes("-topmost", True); self.focus_force(); self.grab_set()
            for d in (150, 300, 600, 900):
                self.after(d, lambda w=self: (w.lift(), w.attributes("-topmost", True), w.focus_force()))
            self.after(1100, lambda w=self: w.attributes("-topmost", False))
        except Exception: pass
        try: self.bell()
        except Exception: pass
        _alog("dialog ready")
    def _open_buy(self):
        import webbrowser
        try: webbrowser.open(self.buy_url)
        except Exception: pass
    def _disable_inputs(self, disabled=True):
        state = "disabled" if disabled else "normal"
        for w in (self.btn_activate, self.btn_buy, self.btn_close):
            try: w.configure(state=state)
            except Exception: pass
    def _do_activate(self):
        email = self.email_var.get().strip(); ref = self.ref_var.get().strip()
        if not email or not ref:
            messagebox.showwarning("Missing info", "Please enter email and reference."); return
        self._disable_inputs(True); self.update_idletasks()
        try: res = activate_with_reference(email, ref)
        except Exception as e: res = {"ok": False, "error": str(e)}
        self._disable_inputs(False)
        if isinstance(res, dict) and res.get("ok"):
            _alog("activation ok"); messagebox.showinfo("Activated", "Activation successful on this PC.")
            cb = self.on_activated; self.destroy()
            if callable(cb):
                try: self.after(0, cb)
                except Exception: cb()
        else:
            err = (isinstance(res, dict) and (res.get("error") or res)) or "Activation failed"
            _alog(f"activation failed: {err}"); messagebox.showerror("Failed", f"Activation failed: {err}")
    def _on_close(self):
        _alog("dialog closed by user")
        try: self.destroy()
        finally: self._open_buy()
