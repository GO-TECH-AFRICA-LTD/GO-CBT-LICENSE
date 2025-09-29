# splash_screen.py — width-safe splash + keyboard/wheel scrolling + LOGO loading overlay
import re
import os
import tkinter as tk
from tkinter import messagebox, ttk

# ---------- Branding & layout knobs ----------
APP_NAME        = "GO CBT APP"
TITLE_TEXT      = "GO CBT APP — Instructions"
WRAP_WIDTH      = 560          # target content width in pixels
CANVAS_HEIGHT   = 360          # visible scroll height
CONTINUE_TEXT   = "Continue"   # button label
AGREE_TEXT      = "I have read and agree to the instructions"

TITLE_FONT      = ("Segoe UI", 16, "bold")
BODY_FONT       = ("Segoe UI", 12)
BUTTON_FONT     = ("Segoe UI", 12, "bold")

BG              = "#f5f7fb"    # content background
WINDOW_BG       = "#ffffff"    # window/frame background
ACCENT_FG       = "#0F62FE"

# Loading overlay text & timing
LOADING_TEXT    = "Preparing your dashboard…"
LOADING_MS      = 3000   # 2.4 seconds (increase/decrease as you like)

# Strict centered size for the loading overlay window
LOADING_WIDTH   = 420
LOADING_HEIGHT  = 280

# Optional icon & asset helpers (best-effort)
try:
    from path_utils import find_app_icon, assets_dir_candidates
except Exception:
    def find_app_icon(): return None
    def assets_dir_candidates():
        here = os.path.dirname(os.path.abspath(__file__))
        return [os.path.join(here, "assets"), here]

# Optional Pillow (for more image formats); Tk PhotoImage handles PNG/GIF on Tk 8.6+
try:
    from PIL import Image, ImageTk
    _HAS_PIL = True
except Exception:
    Image = ImageTk = None
    _HAS_PIL = False

# ---------- Common helpers ----------
def _center_window(win, w=None, h=None):
    try:
        win.update_idletasks()
        if w is None or h is None:
            w = w or win.winfo_reqwidth()
            h = h or win.winfo_reqheight()
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        x, y = max(0, (sw - w) // 2), max(0, (sh - h) // 3)
        win.geometry(f"{max(360, w)}x{max(240, h)}+{x}+{y}")
    except Exception:
        pass

# Insert zero-width break opportunities so long tokens can wrap.
_ZWSP = "\u200b"
def _zwsp_wrap_text(s: str) -> str:
    def soften(token: str) -> str:
        if " " in token:
            return token
        t = token
        t = t.replace("/", "/" + _ZWSP)
        t = t.replace(".", _ZWSP + "." + _ZWSP)
        t = t.replace("@", _ZWSP + "@" + _ZWSP)
        t = t.replace("-", "-" + _ZWSP)
        t = t.replace("_", "_" + _ZWSP)
        return t
    return " ".join(soften(tok) for tok in s.split())

def _find_logo_path():
    names = ("go_cbt_logo.png", "go_cbt_logo.gif", "go_cbt.png", "logo.png", "splash.png", "splash.gif")
    for d in assets_dir_candidates():
        for nm in names:
            p = os.path.join(d, nm)
            if os.path.isfile(p):
                return p
    return None

# ---------------------------------------------------------------------------
# Loading overlay (this is what shows your logo + “Loading your experience…”)
# ---------------------------------------------------------------------------
class _LoadingIntro(tk.Toplevel):
    def __init__(self, master, on_done, duration_ms=LOADING_MS):
        super().__init__(master)
        self.configure(bg=WINDOW_BG)
        # Keep normal window frame (good for focus on Windows), but lock size strictly
        self.overrideredirect(False)
        self.resizable(False, False)
        self._closing = False
        self._on_done = on_done

        # App icon (best-effort)
        try:
            ic = find_app_icon()
            if ic:
                self.iconbitmap(ic)
        except Exception:
            pass

        # Fixed-size interior
        outer = tk.Frame(self, bg=WINDOW_BG)
        outer.pack(fill="both", expand=True)
        # Set strict geometry and prevent auto-resize
        self.geometry(f"{LOADING_WIDTH}x{LOADING_HEIGHT}")
        _center_window(self, LOADING_WIDTH, LOADING_HEIGHT)
        try:
            self.minsize(LOADING_WIDTH, LOADING_HEIGHT)
            self.maxsize(LOADING_WIDTH, LOADING_HEIGHT)
        except Exception:
            pass
        # Constrain inner layout area (leave padding margins)
        pad_x, pad_y = 22, 18
        inner_w = max(200, LOADING_WIDTH  - 2*pad_x)
        inner_h = max(120, LOADING_HEIGHT - 2*pad_y)
        inner = tk.Frame(outer, bg=WINDOW_BG, width=inner_w, height=inner_h, padx=0, pady=0)
        inner.pack(padx=pad_x, pady=pad_y, fill="both", expand=True)
        inner.pack_propagate(False)  # keep fixed size

        # Logo (if found), scaled to fit
        self._img_ref = None
        logo_path = _find_logo_path()
        if logo_path:
            try:
                if _HAS_PIL:
                    from PIL import Image, ImageTk  # local import if available
                    im = Image.open(logo_path)
                    max_logo_w = max(120, inner_w - 140)   # keep space for text & bar
                    if im.width > max_logo_w:
                        ratio = max_logo_w / float(im.width)
                        im = im.resize((int(im.width * ratio), int(im.height * ratio)), Image.LANCZOS)
                    self._img_ref = ImageTk.PhotoImage(im)
                else:
                    self._img_ref = tk.PhotoImage(file=logo_path)
                tk.Label(inner, image=self._img_ref, bg=WINDOW_BG).pack(pady=(0, 8))
            except Exception:
                pass

        # Message (wrap to inner width)
        wrap = max(240, inner_w - 40)
        tk.Label(inner, text=LOADING_TEXT, font=BODY_FONT, bg=WINDOW_BG, wraplength=wrap, justify="center")\
            .pack(pady=(0, 10), fill="x")

        # Indeterminate progressbar sized to inner width
        bar_len = max(180, inner_w - 60)
        pb = ttk.Progressbar(inner, mode="indeterminate", length=bar_len)
        pb.pack()
        try:
            pb.start(11)
        except Exception:
            pass

        # Bring to front and modal-ish
        try:
            self.lift(); self.attributes("-topmost", True); self.focus_force(); self.grab_set()
            self.after(220, lambda: self.attributes("-topmost", False))
        except Exception:
            pass

        # Auto-finish after the configured delay
        self.after(max(200, int(duration_ms)), self._finish)

        # Clean up on close (manual close falls back to finishing)
        self.protocol("WM_DELETE_WINDOW", self._finish)

    def _finish(self):
        if self._closing:
            return
        self._closing = True
        try:
            self.destroy()
        finally:
            cb = self._on_done
            if cb:
                try:
                    self.after(0, cb)
                except Exception:
                    cb()

def show_loading_intro(root, on_done, duration_ms=LOADING_MS):
    """Public API used by main.py: show logo + text + spinner, then call on_done."""
    _LoadingIntro(root, on_done=on_done, duration_ms=duration_ms)

# ---------------------------------------------------------------------------
# Main Splash (read & agree) — width-safe + keyboard/wheel scrolling
# ---------------------------------------------------------------------------
class SplashScreen(tk.Toplevel):
    """
    Scrollable instructions (+ checkbox). Calls on_agree_callback AFTER destroy.
    - Enforces wrap within canvas width (no overflow)
    - Wheel bound only to the canvas, safely unbound on close
    - Arrow keys: ← ↑ → ↓ + PgUp/PgDn + Home/End
    """
    def __init__(self, master=None, on_agree_callback=None, title=TITLE_TEXT):
        super().__init__(master)
        self.transient(master)
        self.title(title)
        self.configure(bg=WINDOW_BG)
        self.resizable(False, False)
        self.on_agree_callback = on_agree_callback

        # safety state
        self._closing = False
        self._mw_bound = False
        self.canvas = None
        self._wrapped_labels = []   # labels whose wraplength we control
        self._content_win_id = None

        # Icon
        try:
            icon = find_app_icon()
            if icon:
                self.iconbitmap(icon)
        except Exception:
            pass

        # ---------- Layout ----------
        outer = tk.Frame(self, padx=14, pady=14, bg=WINDOW_BG)
        outer.pack(fill="both", expand=True)

        title_lbl = tk.Label(outer, text=APP_NAME, font=TITLE_FONT, fg=ACCENT_FG, bg=WINDOW_BG)
        title_lbl.pack(anchor="w", pady=(0, 8))

        sc_frame = tk.Frame(outer, bg=WINDOW_BG)
        sc_frame.pack(fill="both", expand=True)

        canvas = tk.Canvas(sc_frame, borderwidth=0, highlightthickness=0, background=BG, width=WRAP_WIDTH+20, height=CANVAS_HEIGHT)
        vsb = tk.Scrollbar(sc_frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        self.canvas = canvas

        content = tk.Frame(canvas, background=BG)
        self._content_win_id = canvas.create_window((0, 0), window=content, anchor="nw", width=WRAP_WIDTH+20)

        # Keep scrollregion current AND keep the embedded window width equal to canvas width
        def _on_canvas_configure(event):
            try:
                canvas.configure(scrollregion=canvas.bbox("all"))
                canvas.itemconfig(self._content_win_id, width=event.width)
                new_wrap = max(200, event.width - 20)
                for lbl in self._wrapped_labels:
                    try:
                        lbl.configure(wraplength=new_wrap)
                    except Exception:
                        pass
            except Exception:
                pass

        canvas.bind("<Configure>", _on_canvas_configure)

        # ---------- Content (width-safe) ----------
        blocks = [
            "Welcome to GO CBT App!",
            "",
            "Developed by Gbenga O. Olabode (Founder, CEO GO TECH AFRICA LTD)",
            "",
            "Contact Information:",
            "Website: www.gotechafrica.net",
            "Email: gotechafricaltd@gmail.com; info@gotechafrica.net",
            "Phone: 08066713410",
            "",
            "About GO CBT App!",
            "The GO CBT App is a purpose-built software solution created to support FCTA/FCT Civil Service Commission staff in preparing for their promotion examinations.",
            "It offers a realistic simulation of a real Computer-Based Test environment to help users prepare effectively for their exams and allowing them to practice with confidence and familiarity.",
            "",
            "Please read the following instructions carefully:",
            "• Ensure you have a stable environment to take your test.",
            "• You must agree to the instructions before proceeding.",
            "• The test timer will count down once you start.",
            "• Navigate questions using Next, Previous, or question buttons.",
            "• Submit your answers when done or when time expires.",
            "",
            "Wishing you great success as you prepare, practice, and excel!",
        ]

        for line in blocks:
            if not line:
                tk.Label(content, text="", bg=BG).pack(anchor="w", pady=2)
                continue
            txt = _zwsp_wrap_text(line)
            lbl = tk.Label(content, text=txt, bg=BG, font=BODY_FONT, justify="left", wraplength=WRAP_WIDTH)
            lbl.pack(anchor="w", fill="x")
            self._wrapped_labels.append(lbl)

        content.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))

        # ---------- Footer ----------
        footer = tk.Frame(outer, bg=WINDOW_BG)
        footer.pack(fill="x", pady=(10, 0))

        self.agree_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            footer, text=AGREE_TEXT, variable=self.agree_var,
            font=BODY_FONT, bg=WINDOW_BG, activebackground=WINDOW_BG
        ).pack(side="left", anchor="w")

        tk.Button(
            footer, text=CONTINUE_TEXT, font=BUTTON_FONT, command=self.proceed
        ).pack(side="right")

        # --- Ensure footer (checkbox + Continue) is always visible ---
        try:
            self.update_idletasks()
            # Compute desired size from actual content
            content_w = max(WRAP_WIDTH + 20, outer.winfo_reqwidth())
            content_h = outer.winfo_reqheight()
            # Cap window height to 85% of screen; if content exceeds, shrink canvas height
            sh = self.winfo_screenheight()
            max_h = max(360, int(sh * 0.85))
            if content_h > max_h:
                # Reduce canvas height just enough to reveal footer
                delta = min(content_h - max_h + 16, CANVAS_HEIGHT - 160)
                new_canvas_h = max(200, CANVAS_HEIGHT - int(delta))
                try:
                    canvas.configure(height=new_canvas_h)
                    self.update_idletasks()
                    content_h = outer.winfo_reqheight()
                except Exception:
                    pass
            final_w = max(360, int(content_w))
            final_h = max(260, int(min(content_h + 10, max_h)))
            _center_window(self, final_w, final_h)
            try:
                self.minsize(final_w, final_h)
            except Exception:
                pass
        except Exception:
            _center_window(self, int(WRAP_WIDTH * 0.95), CANVAS_HEIGHT + 160)
        try:
            self.lift(); self.attributes("-topmost", True); self.focus_force(); self.grab_set()
            self.after(250, lambda: self.attributes("-topmost", False))
        except Exception:
            pass

        # Safe bindings
        self._bind_scroll(self.canvas)
        self._bind_keys(self.canvas)

        # Cleanup hooks
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Destroy>", self._on_destroy, add="+")

    # ---------- Input bindings ----------
    def _bind_scroll(self, widget):
        if not widget or not widget.winfo_exists() or getattr(self, "_mw_bound", False):
            return
        self._mw_bound = True
        widget.bind("<MouseWheel>", self._on_mousewheel, add="+")   # Win/mac
        widget.bind("<Button-4>", self._on_mousewheel_linux, add="+")  # Linux up
        widget.bind("<Button-5>", self._on_mousewheel_linux, add="+")  # Linux down
        widget.bind("<Enter>", lambda e: (widget.focus_set()), add="+")
        try:
            self.unbind_all("<MouseWheel>")
        except Exception:
            pass

    def _bind_keys(self, widget):
        for seq in ("<Up>", "<Down>", "<Left>", "<Right>", "<Prior>", "<Next>", "<Home>", "<End>"):
            widget.bind(seq, self._on_key_scroll, add="+")

    # ---------- Scrolling handlers ----------
    def _on_mousewheel(self, event):
        if self._closing:
            return "break"
        cv = self.canvas
        if not cv or not cv.winfo_exists():
            return "break"
        steps = int(-1 * (getattr(event, "delta", 0) / 120)) if getattr(event, "delta", 0) else 0
        try:
            if steps:
                cv.yview_scroll(steps, "units")
        except tk.TclError:
            return "break"
        return "break"

    def _on_mousewheel_linux(self, event):
        if self._closing:
            return "break"
        cv = self.canvas
        if not cv or not cv.winfo_exists():
            return "break"
        steps = -1 if getattr(event, "num", 0) == 4 else 1
        try:
            cv.yview_scroll(steps, "units")
        except tk.TclError:
            return "break"
        return "break"

    def _on_key_scroll(self, event):
        if self._closing:
            return "break"
        cv = self.canvas
        if not cv or not cv.winfo_exists():
            return "break"
        seq = event.keysym
        try:
            if seq in ("Up", "Left"):
                cv.yview_scroll(-1, "units")
            elif seq in ("Down", "Right"):
                cv.yview_scroll(1, "units")
            elif seq == "Prior":   # PageUp
                cv.yview_scroll(-1, "pages")
            elif seq == "Next":    # PageDown
                cv.yview_scroll(1, "pages")
            elif seq == "Home":
                cv.yview_moveto(0.0)
            elif seq == "End":
                cv.yview_moveto(1.0)
        except tk.TclError:
            return "break"
        return "break"

    # ---------- Lifecycle ----------
    def proceed(self):
        if not self.agree_var.get():
            messagebox.showwarning("Agreement required", "Please agree to the instructions before proceeding.")
            return
        self._closing = True
        self._unbind_scroll()
        cb = self.on_agree_callback
        try:
            self.destroy()
        finally:
            if cb:
                try:
                    self.after(0, cb)
                except Exception:
                    cb()

    def _unbind_scroll(self):
        if not getattr(self, "_mw_bound", False):
            return
        self._mw_bound = False
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            try:
                if self.canvas and self.canvas.winfo_exists():
                    self.canvas.unbind(seq)
            except Exception:
                pass
        try:
            self.unbind_all("<MouseWheel>")
        except Exception:
            pass

    def _on_close(self):
        self._closing = True
        self._unbind_scroll()
        try:
            self.destroy()
        except Exception:
            pass

    def _on_destroy(self, _evt=None):
        self._closing = True
        self._unbind_scroll()
