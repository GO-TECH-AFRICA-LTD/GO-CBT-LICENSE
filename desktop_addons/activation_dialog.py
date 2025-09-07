import tkinter as tk
from tkinter import messagebox
from license_client import activate_with_reference

PAY_URL = "https://paystack.shop/pay/hpv92fjpxf"

class ActivationDialog(tk.Toplevel):
    def __init__(self, master, buy_url: str = PAY_URL, on_activated=None):
        super().__init__(master)
        self.title("GO CBT APP — Activation")
        self.resizable(False, False)
        self.buy_url = buy_url
        self.on_activated = on_activated

        frm = tk.Frame(self, padx=18, pady=18); frm.pack(fill="both", expand=True)
        tk.Label(frm, text="Enter the email you paid with:").pack(anchor="w")
        self.email_var = tk.StringVar(); tk.Entry(frm, textvariable=self.email_var, width=40).pack(pady=(0,8))
        tk.Label(frm, text="Enter your Paystack payment reference:").pack(anchor="w")
        self.ref_var = tk.StringVar(); tk.Entry(frm, textvariable=self.ref_var, width=40).pack(pady=(0,12))
        tk.Label(frm, text="Note: License binds to this PC. For another PC, purchase another license.", fg="#444").pack(anchor="w", pady=(0,10))
        btns = tk.Frame(frm); btns.pack(fill="x")
        tk.Button(btns, text="Activate", width=12, command=self._do_activate).pack(side="left")
        tk.Button(btns, text="Buy License", width=12, command=self._open_buy).pack(side="right")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _open_buy(self):
        import webbrowser; webbrowser.open(self.buy_url)

    def _do_activate(self):
        email = self.email_var.get().strip(); ref = self.ref_var.get().strip()
        if not email or not ref:
            messagebox.showwarning("Missing info", "Please enter email and reference."); return
        res = activate_with_reference(email, ref)
        if res.get("ok"):
            messagebox.showinfo("Activated", "Activation successful on this PC.")
            self.destroy()
            if callable(self.on_activated):
                self.on_activated()
        else:
            messagebox.showerror("Failed", "Activation failed: {}".format(res.get("error") or res))

    def _on_close(self):
        try: self.master.destroy()
        except: pass
        self.destroy()
