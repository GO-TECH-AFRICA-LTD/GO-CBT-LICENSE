# ---- student_portal.py (PUT NEAR THE TOP, REPLACES any 'from PIL import Image, ImageTk') ----
import os
import tkinter as tk
from tkinter import ttk, messagebox
    # --- Required: Pillow for background image handling (match the working file) ---
# Required for background images
from PIL import Image, ImageTk

# Pillow 10+ / older compatibility
try:
    from PIL.Image import Resampling as _Resampling  # Pillow ≥10
    RESAMPLE_FILTER = _Resampling.LANCZOS
except Exception:
    RESAMPLE_FILTER = getattr(Image, "LANCZOS", getattr(Image, "ANTIALIAS", Image.BICUBIC))

import os, sys, random, json, glob, tempfile, webbrowser

from path_utils import resource_path, asset_path as _pu_asset_path, assets_dir_candidates, find_app_icon
import os, glob, json
from path_utils import assets_dir_candidates

# --- BEGIN: universal question normalizer (place near imports) ----------------
def _ensure_bg_label(self, parent):
    """
    Ensure a background Label exists and is attached to 'parent'.
    Recreate it if it was destroyed.
    """
    # If we don't have a label, or it was destroyed, build a new one
    if getattr(self, "_bg_label", None) is None or not self._bg_label.winfo_exists():
        self._bg_label = tk.Label(parent, bd=0, highlightthickness=0)
        self._bg_label.place(relx=0, rely=0, relwidth=1, relheight=1)

def _normalize_options_dict(opts):
    """
    Accepts options in any of these shapes:
      - dict like {"A": "...", "b": "...", "C":"...", "D":"..."} (any case/order)
      - list like ["A. Text", "B) Text", "C Text", "D - Text"]   (will parse prefixes)
    Returns ordered dict: {"A": "...", "B": "...", "C": "...", "D": "..."}
    Missing items become empty strings (so UI still renders A-D).
    """
    out = {"A": "", "B": "", "C": "", "D": ""}
    if isinstance(opts, dict):
        for k, v in list(opts.items()):
            K = str(k).strip().upper()
            if K in out:
                out[K] = (v if isinstance(v, str) else str(v)).strip()
        return out

    if isinstance(opts, list):
        # try to parse "A. xxx", "B) xxx", "C xxx", etc.
        for raw in opts:
            s = (raw if isinstance(raw, str) else str(raw)).strip()
            if not s:
                continue
            prefix = s[:2].upper()  # "A.", "B)", "C ", "D-"
            letter = None
            if prefix and prefix[0] in "ABCD":
                letter = prefix[0]
                # remove typical separators after the letter
                rest = s[1:].lstrip(".:) -").strip()
                out[letter] = rest
        return out

    # unknown shape: return empty slots
    return out


def _extract_letter_from_answer_field(ans):
    """
    If 'answer' is a letter (A-D), return letter; if it's text, return None (we'll map later).
    """
    if isinstance(ans, str):
        s = ans.strip().upper()
        if s in ("A", "B", "C", "D"):
            return s
    return None


def _map_text_to_letter(options_dict, text):
    """Try to match a free-text correct answer to one of A-D by case-insensitive equality."""
    if not isinstance(text, str):
        text = str(text)
    goal = text.strip().lower()
    for L, opt in options_dict.items():
        if opt.strip().lower() == goal:
            return L
    return None


def normalize_question_item(item):
    """
    Accepts any of your historical item shapes and returns:
      {
        "question": "<text>",
        "options": {"A": "...", "B": "...", "C": "...", "D": "..."},
        "correct": "A" | "B" | "C" | "D"
      }

    Supported inputs:
      - options as dict or list
      - correct letter in:  answer / correct_option / CorrectOption / correct / Correct
      - correct text in:    correct_answer / CorrectAnswer
      - if only text is present, we map it to A-D via options
    """
    qtext = item.get("question") or item.get("Question") or item.get("title") or ""
    opts  = item.get("options", [])
    options_dict = _normalize_options_dict(opts)

    # 1) Try to get a letter straight
    letter = None
    for key in ("correct_option", "CorrectOption", "correct", "Correct"):
        if key in item:
            val = item.get(key)
            if isinstance(val, str) and val.strip().upper() in ("A", "B", "C", "D"):
                letter = val.strip().upper()
                break

    if not letter:
        # 'answer' field can be letter or text
        letter = _extract_letter_from_answer_field(item.get("answer"))

    # 2) If we still don't have a letter, try by matching text
    if not letter:
        corr_text = item.get("correct_answer") or item.get("CorrectAnswer") or ""
        if corr_text:
            letter = _map_text_to_letter(options_dict, corr_text)

    # 3) Final fallback: if 'answer' was text (not letter), try mapping it
    if not letter and isinstance(item.get("answer"), str):
        letter = _map_text_to_letter(options_dict, item["answer"])

    # Guarantee a letter (worst case pick empty 'A' to avoid crash; better than None)
    if letter not in ("A", "B", "C", "D"):
        letter = "A"

    return {
        "question": str(qtext).strip(),
        "options": {
            "A": options_dict.get("A", ""),
            "B": options_dict.get("B", ""),
            "C": options_dict.get("C", ""),
            "D": options_dict.get("D", ""),
        },
        "correct": letter
    }
# --- END: universal question normalizer --------------------------------------

# ------------------------------
# Image resampling compatibility
# ------------------------------
try:
    # Pillow 10+
    from PIL.Image import Resampling as _Resampling
    RESAMPLE_FILTER = _Resampling.LANCZOS
except Exception:
    # Older Pillow
    RESAMPLE_FILTER = getattr(Image, "LANCZOS", getattr(Image, "ANTIALIAS", Image.BICUBIC))

# ------------------------------
# Constants / Styles
# ------------------------------
BASE_FONT        = ("Arial", 12)
BASE_FONT_BOLD   = ("Arial", 13, "bold")
BASE_FONT_LARGE  = ("Arial", 16, "bold")

NAV_BAR_COLOR        = "#004d40"
NAV_BAR_FIXED_HEIGHT = 60
USE_FIXED_HEIGHT_BARS = True  # Toggle this if you want slim bars that persist even without buttons

# ---------------------------------------------
# GIF player & branded Goodbye/Outro screen
# ---------------------------------------------
class GifPlayer(tk.Label):
    def __init__(self, master, gif_path, delay=60, **kwargs):
        super().__init__(master, **kwargs)
        self._frames = []
        i = 0
        while True:
            try:
                frm = tk.PhotoImage(file=gif_path, format=f"gif -index {i}")
                self._frames.append(frm)
                i += 1
            except Exception:
                break
        self._idx = 0
        if self._frames:
            self.config(image=self._frames[0])
            self.after(delay, self._animate, delay)

    def _animate(self, delay):
        if not self._frames:
            return
        self._idx = (self._idx + 1) % len(self._frames)
        self.config(image=self._frames[self._idx])
        self.after(delay, self._animate, delay)


def asset_path(*parts):
    """
    Return a valid path under your asset folders.
    Tries 'assets' first (confirmed folder), then 'assests' (fallback).
    """
    for base in ("assets", "assests"):
        p = resource_path(base, *parts)
        if os.path.exists(p):
            return p
    # final fallback to 'assets' (helps produce a clear error if truly missing)
    return resource_path("assets", *parts)

def _norm_name(s: str) -> str:
    """lowercase alnum only, so 'Financial Regulations_clean.json' ~ 'financialregulationsjson'"""
    return "".join(ch for ch in s.lower() if ch.isalnum())

def _strip_common_suffixes(s: str) -> str:
    # Allow matching with or without _clean/_normalized, etc.
    for token in ("clean", "normalized", "normalised"):
        s = s.replace(token, "")
    return s

def find_json_file(preferred_name: str) -> str | None:
    """
    1) Try exact match in any candidate assets dir
    2) Fuzzy match ignoring case/spacing/_clean/_normalized
    """
    # 1) exact
    for d in assets_dir_candidates():
        p = os.path.join(d, preferred_name)
        if os.path.exists(p):
            return p

    # 2) fuzzy
    want = _strip_common_suffixes(_norm_name(preferred_name))
    for d in assets_dir_candidates():
        for f in glob.glob(os.path.join(d, "*.json")):
            base = os.path.basename(f)
            nb = _strip_common_suffixes(_norm_name(base))
            if nb == want or want in nb or nb in want:
                return f
    return None

class GoodbyeScreen(tk.Frame):
    def __init__(self, master, on_exit, auto_close_ms=4000):
        super().__init__(master, bg="#0b1020")
        self.on_exit = on_exit
        self._build_ui()
        if auto_close_ms:
            self.after(auto_close_ms, self.on_exit)

    def _build_ui(self):
        wrap = tk.Frame(self, bg="#0b1020")
        wrap.pack(expand=True)

        # Try preferred logo name, then fallback to existing "logo.png"
        logo_path = asset_path("go_cbt_logo.png")
        if not os.path.exists(logo_path):
            logo_path = asset_path("logo.png")

        try:
            if os.path.exists(logo_path):
                img = Image.open(logo_path)
                img.thumbnail((260, 260))
                self._logo = ImageTk.PhotoImage(img)
                tk.Label(wrap, image=self._logo, bg="#0b1020").pack(pady=(12, 10))
        except Exception:
            pass

        tk.Label(
            wrap,
            text="Thank you for using\nGO CBT APP",
            font=("Segoe UI", 24, "bold"),
            fg="#ffffff",
            bg="#0b1020",
            justify="center"
        ).pack(pady=(0, 8))

        tk.Label(
            wrap,
            text="Your Exam Success Partner",
            font=("Segoe UI", 14),
            fg="#b7c0d8",
            bg="#0b1020"
        ).pack(pady=(0, 14))

        # Optional animated GIF (place at assets/thank_you.gif)
        gif_path = asset_path("thank_you.gif")
        if os.path.exists(gif_path):
            GifPlayer(wrap, gif_path, delay=60, bg="#0b1020").pack(pady=6)

        tk.Label(
            wrap,
            text="Closing in a moment…",
            font=("Segoe UI", 11),
            fg="#9fb0cf",
            bg="#0b1020"
        ).pack(pady=(12, 6))

        tk.Button(
            wrap,
            text="Exit Now",
            font=("Segoe UI", 12, "bold"),
            command=self.on_exit
        ).pack(pady=(2, 18))


class GO_CBT_App(tk.Frame):
    def __init__(self, master=None):
        super().__init__(master)
        self.master = master
        self.master.title("GO CBT APP")
        self.pack(fill="both", expand=True)

        try:
            _icon = find_app_icon()
            if _icon:
                self.master.iconbitmap(_icon)
        except Exception:
            pass

        self.student_name = ""
        self.full_question_bank = self.load_full_question_bank()
        self.questions = {}
        self.answers = {}
        self.current_subject = None
        self.current_question_index = 0
        self.timer_id = None
        self._timer_after_id = None
        self.bind("<Destroy>", self._on_destroy, add="+")
        self.selected_option = tk.StringVar()
        self.nav_buttons = []
        self.cycle_start_indices = {}

        # Background holders
        self._bg_src = None
        self._bg_tk = None
        self._bg_label = None

        # Shuffle question bank once
        self.shuffled_question_bank = {}
        for subject, questions in self.full_question_bank.items():
            shuffled = questions[:]
            random.shuffle(shuffled)
            self.shuffled_question_bank[subject] = shuffled

        # Default: Close X behaves normally unless overridden on Results screen
        self._bind_close_x_to(self.master.destroy)

    # ---------- Window-close helpers ----------
    def _bind_close_x_to(self, handler):
        try:
            self.master.protocol("WM_DELETE_WINDOW", handler)
        except Exception:
            pass

    def _bind_close_to_default(self):
        self._bind_close_x_to(self.master.destroy)
        
        # ---------- Window-close helpers ----------
    def stop_timer(self):
        """Cancel any scheduled timer tick."""
        aid = getattr(self, "_timer_after_id", None)
        if aid:
            try:
                self.after_cancel(aid)
            except Exception:
                pass
            self._timer_after_id = None

    def _on_destroy(self, _evt=None):
        """Ensure timers are cancelled when this widget goes away."""
        try:
            self.stop_timer()
        except Exception:
            pass

    # ---------- General helpers ----------
    def disable_all_buttons(self):
        for widget in self.winfo_children():
            if isinstance(widget, tk.Button):
                widget.config(state="disabled")

    def enable_all_buttons(self):
        for widget in self.winfo_children():
            if isinstance(widget, tk.Button):
                widget.config(state="normal")

    def clear_widgets(self):
        # existing code that destroys children...
        for child in self.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        # 🔧 make sure stale refs don’t linger
        self._bg_label = None
        self._bg_img = None
        self._bg_tk = None
        
    def on_data_ready(self):
        """
        Safe default handler called when question-bank loading finishes.
        It attempts a few non-destructive actions to make the portal visible.
        """
        try:
            # diagnostic log
            try:
                if 'diag_log' in globals():
                    diag_log("on_data_ready: called")
            except Exception:
                pass

            # 1) Ensure the root/toplevel is visible
            try:
                # if we have a top-level window
                if hasattr(self, "deiconify") and callable(getattr(self, "deiconify")):
                    try: self.deiconify()
                    except Exception: pass
                # focus window if possible
                try:
                    if hasattr(self, "focus_force") and callable(getattr(self, "focus_force")):
                        try: self.focus_force()
                        except Exception: pass
                except Exception:
                    pass
            except Exception:
                pass

            # 2) Try to lift or pack the main_frame (common pattern)
            try:
                if hasattr(self, "main_frame"):
                    try:
                        mf = getattr(self, "main_frame")
                        try:
                            mf.lift()
                        except Exception:
                            pass
                        try:
                            # if not managed by pack/grid, attempt pack (best-effort)
                            mf.pack(fill="both", expand=True)
                        except Exception:
                            pass
                    except Exception:
                        pass
            except Exception:
                pass

            # 3) Call common builder methods if they exist (non-destructive)
            for candidate in ("build_main_ui", "build_ui", "render_portal", "render_ui", "show_portal", "create_widgets", "setup_ui"):
                try:
                    if hasattr(self, candidate) and callable(getattr(self, candidate)):
                        try:
                            if 'diag_log' in globals(): diag_log(f"on_data_ready: calling {candidate}()")
                            getattr(self, candidate)()
                            if 'diag_log' in globals(): diag_log(f"on_data_ready: {candidate}() succeeded")
                            # stop after first successful builder
                            return
                        except Exception as e:
                            try:
                                if 'diag_log' in globals(): diag_log(f"on_data_ready: {candidate}() failed: {repr(e)}")
                            except Exception:
                                pass
                except Exception:
                    pass

            # 4) Enable a typical start button if present (best-effort)
            try:
                if hasattr(self, "start_button"):
                    try:
                        sb = getattr(self, "start_button")
                        try:
                            sb.configure(state="normal")
                            try: sb.focus_set()
                            except Exception: pass
                        except Exception:
                            pass
                    except Exception:
                        pass
            except Exception:
                pass

            # 5) Final diagnostic fallback – list some attributes
            try:
                if 'diag_log' in globals():
                    try:
                        attrs = [n for n in dir(self) if not n.startswith("_")]
                        diag_log("on_data_ready: post-hook attributes snapshot: " + ", ".join(attrs))
                    except Exception:
                        pass
            except Exception:
                pass

        except Exception as e:
            try:
                if 'diag_log' in globals():
                    diag_log("on_data_ready: unexpected error: " + repr(e))
            except Exception:
                pass

    # ---------- Question bank loader ----------
    def load_full_question_bank(self):
        """
        Load all subject JSON files from assets/ or _internal/assets/.
        Returns: dict[str, list[dict]]
        """
        def load_questions_by_filename(preferred_filename: str) -> list[dict]:
            """
            Locate a subject JSON by name (exact or fuzzy) and return a list of normalized questions.
            Normalized shape:
              { "question": str, "options": {"A","B","C","D"}, "correct": "A"|"B"|"C"|"D" }
            """
            # --- helper: tolerant finder ---
            def _norm_name(s: str) -> str:
                return "".join(ch for ch in s.lower() if ch.isalnum())

            def _strip_common_suffixes(s: str) -> str:
                for t in ("clean", "normalized", "normalised"):
                    s = s.replace(t, "")
                return s

            def _find_json_file(name: str) -> str | None:
                # 1) exact match in any asset dir
                for d in assets_dir_candidates():
                    p = os.path.join(d, name)
                    if os.path.exists(p):
                        return p
                # 2) fuzzy match
                want = _strip_common_suffixes(_norm_name(name))
                for d in assets_dir_candidates():
                    for f in glob.glob(os.path.join(d, "*.json")):
                        base = os.path.basename(f)
                        nb = _strip_common_suffixes(_norm_name(base))
                        if nb == want or want in nb or nb in want:
                            return f
                return None

            # --- resolve file path ---
            path = _find_json_file(preferred_filename)
            if not path or not os.path.exists(path):
                print(f"[WARN] Asset not found for: {preferred_filename}")
                print("[WARN] Looked in:", assets_dir_candidates())
                return []

            # --- read JSON safely ---
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                print(f"[ERROR] Unable to read {path}: {e}")
                return []

            # unwrap {"questions": [...]} shape if present
            if isinstance(data, dict) and "questions" in data:
                data = data["questions"]

            # --- normalize in a SINGLE loop; avoid duplicates ---
            questions: list[dict] = []
            seen = set()
            for raw in data:
                try:
                    norm = normalize_question_item(raw)  # your universal normalizer at module top
                    opts = norm.get("options", {})
                    key = (
                        norm.get("question", "").strip(),
                        opts.get("A", "").strip(),
                        opts.get("B", "").strip(),
                        opts.get("C", "").strip(),
                        opts.get("D", "").strip(),
                        (norm.get("correct") or "").strip().upper(),
                    )
                    if key in seen:
                        continue
                    seen.add(key)
                    questions.append(norm)
                except Exception:
                    # skip malformed rows quietly
                    continue

            print(f"[INFO] Loaded {len(questions)} from {os.path.basename(path)}")
            return questions

                    # === END OF NEW BLOCK ===
            
        full_bank = {}
        # Map subjects → intended filenames (finder is fuzzy about case/spacing/underscores)
        full_bank["Current Affairs"] = load_questions_by_filename("Nigerian_Current_Affairs_Full.json")
        full_bank["Code of Conduct"] = load_questions_by_filename("Code_of_Conduct_Questions_1-400.json")
        full_bank["Nigerian Tax"] = load_questions_by_filename("NIGERIAN_TAX_MCQs.json")
        full_bank["Leadership"] = load_questions_by_filename("Leadership.json")
        full_bank["Computer Knowledge"] = load_questions_by_filename("Computer.json")
        full_bank["Psychometrics"] = load_questions_by_filename("Psychometrics.json")
        full_bank["Financial Regulations"] = load_questions_by_filename("Financial Regulations.json")
        full_bank["Public Procurement"] = load_questions_by_filename("Public Procurement.json")
        full_bank["Federal Civil Service Strategic Implementation Plan 2025"] = load_questions_by_filename("FCSSIP25_MCQs.json")
        full_bank["CBN and Monetary Policy"] = load_questions_by_filename("CBN AND MONETARY POLICIES.json")
        full_bank["FCTA and It's Operations"] = load_questions_by_filename("FCTA AND ITS OPERATIONS.json")
        full_bank["Comprehensive Competency Framework"] = load_questions_by_filename("CCF_100_MCQs.json")
        full_bank["Public Service Rules"] = load_questions_by_filename("PSR.json")
        full_bank["Education Profession"] = load_questions_by_filename("Education_Sector.json")
        full_bank["Medical/Health Profession"] = load_questions_by_filename("Health_MCQs.json")
        full_bank["Tourism Development, Arts & Culture Profession"] = load_questions_by_filename("TAC_MCQs.json")
        full_bank["Transportation & Vehicle Inspection Profession"] = load_questions_by_filename("Transport_MCQs.json")
        full_bank["Lands, Housing & Urban Development Profession"] = load_questions_by_filename("URP_MCQs.json")
        full_bank["Agriculture, Rural Development and Infrastructure Profession"] = load_questions_by_filename("Agric_MCQs.json")
        full_bank["Social Welfare & Community Development Profession"] = load_questions_by_filename("Social_MCQs.json")
        full_bank["Human Resource Management (Admin) Profession"] = load_questions_by_filename("HRM_MCQs.json")
        full_bank["Engineering Profession"] = load_questions_by_filename("Engineering_MCQs.json")
        full_bank["Civil Service Reforms & Policies"] = load_questions_by_filename("CCRP_MCQs.json")
        full_bank["Fire Service Profession"] = load_questions_by_filename("Fire_Service_MCQs.json")
        full_bank["General Knowledge"] = load_questions_by_filename("General Knowledge MCQs.json")
        full_bank["Expanded FCTA Structure & Functions"] = load_questions_by_filename("Expanded FCTA Structure & Functions.json")
        full_bank["Legal Profession"] = load_questions_by_filename("Legal_MCQs.json")
        full_bank["Finance & Account, Budget and Audit Profession"] = load_questions_by_filename("Accounting_MCQs.json")
        full_bank["Architectural Profession"] = load_questions_by_filename("Architecture.json")
        full_bank["Information and Communication Technology Profession"] = load_questions_by_filename("ICT.json")
        full_bank["General Mock Test for All"] = load_questions_by_filename("GMT.json")
        full_bank["Surveying Profession"] = load_questions_by_filename("Surveying.json")
        full_bank["Journalism Profession"] = load_questions_by_filename("Journalism.json")
        full_bank["Public Relations Profession"] = load_questions_by_filename("Public Relations.json")
        full_bank["Guidance & Counselling and Librarianship Professions"] = load_questions_by_filename("Guidance_Library_MCQs.json")
        full_bank["Community & Public Health Profession"] = load_questions_by_filename("Community_Public_Health_MCQs.json")
        full_bank["Environmental & Utilities Profession"] = load_questions_by_filename("Environment_Utilities_MCQs.json")
        full_bank["Compliance/Regulatory Profession"] = load_questions_by_filename("Compliance_Regulatory_MCQs.json")
        full_bank["Planning, Research & Statistics (PRS) Profession"] = load_questions_by_filename("Planning_Research_Statistics_MCQs.json")
        full_bank["Protocol & Liaison, Public Affairs and Customer Service Profession"] = load_questions_by_filename("Protocol_PublicAffairs_CustomerService_MCQs.json")

        return full_bank

    # ---------- Login Page ----------
    def show_login_page(self):
        self._bind_close_to_default()
        self.clear_widgets()

        # Centered minimal box
        box = tk.Frame(self, bd=2, relief="groove", padx=20, pady=20)
        box.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(box, text="Enter Your Full Name (for Practice Purpose):", font=BASE_FONT_BOLD).pack(pady=(0, 10))
        self.name_entry = tk.Entry(box, font=BASE_FONT, width=40)
        self.name_entry.pack(pady=(0, 10))
        self.name_entry.focus_set()

        # Instruction lines
        tk.Label(
            box,
            text="You will be required to repeat the same process each time you practice with this app.",
            font=BASE_FONT,
            wraplength=400,
            justify="left",
            fg="blue"
        ).pack(pady=(5, 5))

        tk.Label(
            box,
            text="During your REAL EXAM, enter the exam number issued by the FCT Civil Service Commission.\n"
                 "If a different name appears, call for help immediately.",
            font=BASE_FONT,
            wraplength=400,
            justify="left",
            fg="red"
        ).pack(pady=(5, 5))

        tk.Label(
            box,
            text="Your REAL EXAM NUMBER should look like:\nFCT-CSC/AA/C.0000/00/00/000000/AA",
            font=BASE_FONT,
            wraplength=400,
            justify="left",
            fg="green"
        ).pack(pady=(5, 10))

        start_btn = tk.Button(box, text="Start Exam", font=BASE_FONT_BOLD, command=self.start_exam)
        start_btn.pack(pady=(5, 0))

    def start_exam(self):
        name = self.name_entry.get().strip()
        if not name:
            messagebox.showwarning("Input Required", "Please enter your full name to continue.")
            return
        self.student_name = name
        self.show_subject_selection()

    # ---------- Subject Selection ----------
    def show_subject_selection(self):
        self._bind_close_to_default()
        self.clear_widgets()
        select_frame = tk.Frame(self)
        select_frame.pack(fill="both", expand=True, padx=20, pady=20)

        welcome_msg = (
            f"Welcome {self.student_name}\n"
            "Below are subjects like Current Affairs, Leadership, Computer Knowledge, Psychometrics, Financial Regulations, Public Procurement, Civil Service Reforms and Policies, FCSSIP-25, "
            "CBN and Monetary Policy, FCTA & Its Operations, Public Service Rules, Code of Conduct, Comprehensive Competency Framework, Nigerian Tax, "
            "and some specialized professions like Education, Engineering, Transportation, Human Resource Management, Health, Social, Urban & Regional Planning, Tourism, Arts & Culture, Agric etc\n"
            "Select your subject from the list and click Load Selected Subject or Simply double-click on any subject in the list to open it.\n"
            "OR\n"
            "Click LOAD SIMULATION EXAM for a mixed 100 questions across subjects excluding Professional Questions:\n"
        )

        # ---- Dynamic wrap label (fits window width) ----
        label = tk.Label(
            select_frame,
            text=welcome_msg,
            font=BASE_FONT_BOLD,
            justify="left",
            wraplength=1  # temporary; will be set after layout & on resize
        )
        label.pack(pady=(0, 10), anchor="w", fill="x")

        # Set initial wraplength once the frame knows its width
        def _set_initial_wrap():
            w = max(300, select_frame.winfo_width() - 40)  # subtract padding
            label.config(wraplength=w)
        self.after(0, _set_initial_wrap)

        # Update wraplength whenever the container resizes
        def _on_resize(event):
            new_wrap = max(300, event.width - 40)
            if label.cget("wraplength") != new_wrap:
                label.config(wraplength=new_wrap)
        select_frame.bind("<Configure>", _on_resize)

        # ---- Quick search / filter ----
        search_frame = tk.Frame(select_frame)
        search_frame.pack(fill="x", pady=(0, 8))
        tk.Label(search_frame, text="Search:", font=BASE_FONT).pack(side="left")
        self.subject_search_var = tk.StringVar()
        search_entry = tk.Entry(search_frame, textvariable=self.subject_search_var, font=BASE_FONT, width=30)
        search_entry.pack(side="left", padx=8)

        # ---- Scrollable list of subjects ----
        list_container = tk.Frame(select_frame, borderwidth=1, relief="groove")
        list_container.pack(fill="both", expand=True, pady=(0, 12))

        self.subject_listbox = tk.Listbox(list_container, font=BASE_FONT, activestyle="dotbox")
        yscroll = tk.Scrollbar(list_container, orient="vertical", command=self.subject_listbox.yview)
        self.subject_listbox.configure(yscrollcommand=yscroll.set)

        self.subject_listbox.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")

        # Cache & populate subjects
        self._all_subjects_sorted = sorted(self.full_question_bank.keys())
        for subj in self._all_subjects_sorted:
            self.subject_listbox.insert("end", subj)

        # Live filter
        def _apply_subject_filter(*_):
            q = (self.subject_search_var.get() or "").strip().lower()
            self.subject_listbox.delete(0, "end")
            for subj in self._all_subjects_sorted:
                if q in subj.lower():
                    self.subject_listbox.insert("end", subj)
        self.subject_search_var.trace_add("write", _apply_subject_filter)

        # Double-click to load
        def _on_double_click(event):
            self.load_selected_subject()
        self.subject_listbox.bind("<Double-Button-1>", _on_double_click)

        # ---- Action buttons ----
        btns = tk.Frame(select_frame)
        btns.pack(pady=6)

        load_btn = tk.Button(btns, text="Load Selected Subject",
                             font=BASE_FONT_BOLD, command=self.load_selected_subject)
        load_btn.pack(side="left", padx=8)

        load_sim_btn = tk.Button(btns, text="Load Simulation Exam (Mixed 100 Questions)",
                                 font=BASE_FONT_BOLD, bg="#007acc", fg="white",
                                 command=self.load_simulation_exam)
        load_sim_btn.pack(side="left", padx=8)

    def load_selected_subject(self):
        # Prefer Listbox selection if present
        if hasattr(self, "subject_listbox") and self.subject_listbox.size() > 0:
            sel = self.subject_listbox.curselection()
            subject = self.subject_listbox.get(sel[0]) if sel else None
        else:
            # Fallback if ever called before Listbox exists
            subject = getattr(self, "subject_var", None).get() if hasattr(self, "subject_var") else None

        if not subject or subject not in self.full_question_bank:
            messagebox.showwarning("Invalid Selection", "Please select a valid subject from the list.")
            return
        self.load_questions_for_subject(subject)

    def load_simulation_exam(self):
        all_questions = []
        for subject, qlist in self.full_question_bank.items():
            # Skip any subject that ends with "Profession"
            if subject.strip().lower().endswith("profession"):
                continue
            all_questions.extend(qlist)

        if len(all_questions) < 100:
            messagebox.showerror("Activation required", "Your GO CBT APP license is not active on this PC. Click OK to open the purchase page for simulation exam.")
            return

        random.shuffle(all_questions)
        self.current_subject = "Simulation Exam"
        self.questions[self.current_subject] = all_questions[:100]
        self.answers[self.current_subject] = [None] * 100
        self.current_question_index = 0
        self.show_exam_window()
        
    def audit_loaded_subjects(app):
        print("\n=== GO CBT Question Bank Audit ===")
        for subj, qlist in app.full_question_bank.items():
            total = len(qlist)
            bad = 0
            for q in qlist:
                opts = q.get("options", {})
                letter = (q.get("correct") or "").strip().upper()
                if set(opts.keys()) != {"A", "B", "C", "D"} or letter not in ("A", "B", "C", "D"):
                    bad += 1
            print(f"{subj}: total={total}, bad={bad}")
        print("=== Audit Complete ===\n")

    def load_questions_for_subject(self, subject):
        self.current_subject = subject

        questions_pool = self.shuffled_question_bank.get(subject, [])
        if len(questions_pool) == 0:
            messagebox.showerror("Activation required", "Your GO CBT APP license is not active on this PC. Click OK to open the purchase page.")
            return

        start_index = self.cycle_start_indices.get(subject, 0)
        if start_index + 100 > len(questions_pool):
            selected = questions_pool[start_index:] + questions_pool[:(start_index + 100) % len(questions_pool)]
            self.cycle_start_indices[subject] = (start_index + 100) % len(questions_pool)
        else:
            selected = questions_pool[start_index:start_index + 100]
            self.cycle_start_indices[subject] = start_index + 100

        self.questions[subject] = selected
        self.answers[subject] = [None] * len(selected)
        self.current_question_index = 0

        self.show_exam_window()

    # ---------- Background handling for Exam Window ----------
    def _setup_exam_background(self):
        """
        Create/refresh the background image for the exam window.
        - Looks up assets/exam_bg.(png|jpg), cbt_bg.(png|jpg), or bg.(png|jpg)
        - Resizes with Pillow on window <Configure>
        - Keeps references to avoid GC
        - Falls back to a friendly solid color if not found/failed
        """
        import os, tkinter as tk
        from path_utils import asset_path

        parent = self  # draw under the main frame

        # 1) Candidate files in assets/
        candidates = ["exam_bg.jpg", "exam_bg.png", "cbt_bg.jpg", "cbt_bg.png", "bg.jpg", "bg.png"]
        bg_path = None
        for name in candidates:
            p = asset_path(name)
            if os.path.exists(p):
                bg_path = p
                break

        # 2) No image -> remove label and use a soft color
        if not bg_path:
            try:
                if getattr(self, "_bg_label", None) and self._bg_label.winfo_exists():
                    self._bg_label.destroy()
            except Exception:
                pass
            self._bg_label = None
            self._bg_src = None
            self._bg_tk = None
            try:
                self.configure(bg="#e9f3ff")
            except Exception:
                pass
            return

        # 3) Ensure a background label exists
        if getattr(self, "_bg_label", None) is None or not self._bg_label.winfo_exists():
            self._bg_label = tk.Label(parent, bd=0, highlightthickness=0)
            self._bg_label.place(relx=0, rely=0, relwidth=1, relheight=1)

        # 4) Load source image
        try:
            self._bg_src = Image.open(bg_path).convert("RGBA")
        except Exception:
            try:
                if getattr(self, "_bg_label", None) and self._bg_label.winfo_exists():
                    self._bg_label.destroy()
            except Exception:
                pass
            self._bg_label = None
            self._bg_src = None
            self._bg_tk = None
            try:
                self.configure(bg="#e9f3ff")
            except Exception:
                pass
            return

        # 5) Render current size
        w = max(1, parent.winfo_width() or 1)
        h = max(1, parent.winfo_height() or 1)
        try:
            img = self._bg_src.resize((w, h), RESAMPLE_FILTER)
        except Exception:
            img = self._bg_src
        self._bg_tk = ImageTk.PhotoImage(img)

        if getattr(self, "_bg_label", None) is None or not self._bg_label.winfo_exists():
            self._bg_label = tk.Label(parent, bd=0, highlightthickness=0)
            self._bg_label.place(relx=0, rely=0, relwidth=1, relheight=1)

        try:
            self._bg_label.configure(image=self._bg_tk)
            self._bg_label.image = self._bg_tk   # keep reference
            self._bg_label.lower()               # behind content
        except Exception:
            pass

        # 6) Bind resize (replace any existing binding)
        try:
            if hasattr(self, "_bg_bind_id") and self._bg_bind_id:
                try:
                    self.unbind("<Configure>", self._bg_bind_id)
                except Exception:
                    pass
        except Exception:
            pass

        def _on_resize(evt):
            if not getattr(self, "_bg_label", None) or not self._bg_label.winfo_exists():
                return
            if not getattr(self, "_bg_src", None):
                return
            if evt.width <= 1 or evt.height <= 1:
                return
            try:
                img2 = self._bg_src.resize((evt.width, evt.height), RESAMPLE_FILTER)
                self._bg_tk = ImageTk.PhotoImage(img2)
                if self._bg_label and self._bg_label.winfo_exists():
                    self._bg_label.configure(image=self._bg_tk)
                    self._bg_label.image = self._bg_tk
            except Exception:
                pass

        try:
            self._bg_bind_id = self.bind("<Configure>", _on_resize)
        except Exception:
            pass

    # ---------- Exam Window ----------
    def show_exam_window(self):
        self._setup_exam_background()
    # ... then create/pack your content frames on top
        self._bind_close_to_default()
        self.clear_widgets()

        # Background image
        self._setup_exam_background()

        # --- Main content frame ---
        content_frame = tk.Frame(self)
        content_frame.pack(fill="both", expand=True, padx=40, pady=20)

        header = tk.Frame(content_frame, bg=NAV_BAR_COLOR)
        header.pack(fill="x")

        tk.Label(header, text=f"Student: {self.student_name}", fg="white", bg=NAV_BAR_COLOR,
                 font=BASE_FONT_BOLD).pack(side="left", padx=20, pady=10)
        submit_btn = tk.Button(header, text="Submit", command=self.confirm_submit,
                               font=BASE_FONT, width=12)
        submit_btn.pack(side="right", padx=(0, 10), pady=10)
        self.timer_label = tk.Label(header, text="", fg="white", bg=NAV_BAR_COLOR,
                                    font=BASE_FONT_BOLD)
        self.timer_label.pack(side="right", padx=20, pady=10)

        self.start_timer(3600)  # 1 hour

        # --- Question display area ---
        self.question_area = tk.Frame(content_frame)
        self.question_area.pack(pady=20, fill="both", expand=True)

        self.question_number_label = tk.Label(
            self.question_area, font=BASE_FONT_LARGE, wraplength=850, justify="left"
        )
        self.question_number_label.pack(anchor="w", padx=30, pady=10)

        self.question_text_label = tk.Label(
            self.question_area, font=BASE_FONT, wraplength=850, justify="left"
        )
        self.question_text_label.pack(anchor="w", padx=30, pady=(0, 30))

        self.selected_option = tk.StringVar()
        self.option_rbs = {}
        for opt in ['A', 'B', 'C', 'D']:
            rb = tk.Radiobutton(
                self.question_area, text="", variable=self.selected_option, value=opt,
                font=BASE_FONT, selectcolor="#cde1f9",
                command=self.save_current_answer
            )
            rb.pack(anchor="w", padx=20, pady=8)
            self.option_rbs[opt] = rb

        
        # --- Nav bar (TOP) — keep frame; WITH Prev/Next buttons ---
        nav_frame_top = tk.Frame(content_frame, bg=NAV_BAR_COLOR)
        nav_frame_top.pack(pady=10, fill='x', expand=True)
        button_container_top = tk.Frame(nav_frame_top, bg=NAV_BAR_COLOR)
        button_container_top.pack(anchor='center', fill='x')

        if USE_FIXED_HEIGHT_BARS:
            button_container_top.configure(height=NAV_BAR_FIXED_HEIGHT)
            button_container_top.pack_propagate(False)

        # Add Prev/Next on TOP bar only
        tk.Button(button_container_top, text="Previous", command=self.prev_question,
                  font=BASE_FONT, width=10).pack(side="left", padx=20, pady=8)
        tk.Button(button_container_top, text="Next", command=self.next_question,
                  font=BASE_FONT, width=10).pack(side="left", padx=20, pady=8)

        # --- Number grid (1..N) ---

        nav_buttons_outer = tk.Frame(content_frame)
        nav_buttons_outer.pack(pady=10)
        self.nav_buttons_frame = tk.Frame(nav_buttons_outer)
        self.nav_buttons_frame.pack()

        q_count = len(self.questions.get(self.current_subject, []))
        cols = 25
        self.nav_buttons = []
        for i in range(q_count):
            row = i // cols
            col = i % cols
            btn = tk.Button(self.nav_buttons_frame, text=str(i + 1), width=3, font=BASE_FONT,
                            command=lambda i=i: self.go_to_question(i))
            btn.grid(row=row, column=col, padx=2, pady=2)
            self.nav_buttons.append(btn)
        for c in range(cols):
            self.nav_buttons_frame.grid_columnconfigure(c, weight=1)

        # --- Nav bar (BOTTOM) — keep frame; no Prev/Next buttons ---
        nav_frame_bottom = tk.Frame(content_frame, bg=NAV_BAR_COLOR)
        nav_frame_bottom.pack(pady=10, fill='x', expand=True)

        button_container_bottom = tk.Frame(nav_frame_bottom, bg=NAV_BAR_COLOR)
        button_container_bottom.pack(anchor='center', fill='x')

        if USE_FIXED_HEIGHT_BARS:
            button_container_bottom.configure(height=NAV_BAR_FIXED_HEIGHT)
            button_container_bottom.pack_propagate(False)

        # Finally show Q1
        self.load_question(self.current_question_index)

    # ---------- Answer storage ----------
    def _initialize_empty_answers(self):
        self.answers = {}
        for subject, q_list in self.questions.items():
            self.answers[subject] = [None] * len(q_list)

    def save_answers_to_file(self):
        if not self.student_name:
            return
        save_path = f"{self.student_name}_answers.json"
        try:
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(self.answers, f)
        except Exception as e:
            print(f"Error saving answers: {e}")

    # ---------- Question navigation and loading ----------
    def save_current_answer(self):
        if self.current_subject is None:
            return
        selected = self.selected_option.get()
        if selected == "":
            selected = None
        self.answers[self.current_subject][self.current_question_index] = selected

    def load_question(self, index):
        q_list = self.questions.get(self.current_subject, [])
        if not q_list or index >= len(q_list):
            return
        question = q_list[index]
        self.current_question_index = index
        self.selected_option.set(self.answers[self.current_subject][index] or "")

        self.question_number_label.config(text=f"Question {index + 1} of {len(q_list)}")
        self.question_text_label.config(text=question.get("question", ""))
        for opt in ['A', 'B', 'C', 'D']:
            text = question["options"].get(opt, "")
            self.option_rbs[opt].config(text=f"{opt}. {text}")

        self.update_nav_buttons()

    def update_nav_buttons(self):
        q_count = len(self.questions[self.current_subject])
        for i in range(q_count):
            btn = self.nav_buttons[i]
            answer = self.answers[self.current_subject][i]
            if i == self.current_question_index:
                btn.config(bg="#0000ff", fg="white")
            elif answer is not None and answer != "":
                btn.config(bg="#008000", fg="white")
            else:
                btn.config(bg="#ff0000", fg="white")

    def next_question(self):
        try:
            self.disable_all_buttons()
            self.save_current_answer()
            if self.current_question_index < len(self.questions[self.current_subject]) - 1:
                self.current_question_index += 1
                self.load_question(self.current_question_index)
            self.enable_all_buttons()
        except tk.TclError:
            pass

    def prev_question(self):
        try:
            self.disable_all_buttons()
            self.save_current_answer()
            if self.current_question_index > 0:
                self.current_question_index -= 1
                self.load_question(self.current_question_index)
            self.enable_all_buttons()
        except tk.TclError:
            pass

    def go_to_question(self, index):
        try:
            self.disable_all_buttons()
            self.save_current_answer()
            self.current_question_index = index
            self.load_question(index)
            self.enable_all_buttons()
        except tk.TclError:
            pass

    # ---------- Timer ----------
        # ---------- Timer ----------
    def start_timer(self, seconds):
        """Start/restart the exam countdown."""
        import time
        self.exam_end_ts = time.time() + int(seconds)
        self.stop_timer()  # clear any old one
        self._timer_after_id = self.after(1000, self.update_timer)

    def update_timer(self):
        """Safe ticking timer; survives navigation and window closes."""
        # Label guard
        lbl = getattr(self, "timer_label", None)
        if not lbl:
            self.stop_timer()
            return
        try:
            if not lbl.winfo_exists():
                self.stop_timer()
                return
        except Exception:
            self.stop_timer()
            return

        # Compute remaining
        import time
        end_ts = getattr(self, "exam_end_ts", None)
        remaining = max(0, int(end_ts - time.time())) if end_ts else 0
        mins, secs = divmod(remaining, 60)
        hrs, mins = divmod(mins, 60)
        time_format = f"{hrs:02}:{mins:02}:{secs:02}"

        # Update label safely
        try:
            lbl.config(text=time_format)
        except tk.TclError:
            self.stop_timer()
            return

        # Time up?
        if remaining <= 0:
            self.stop_timer()
            if hasattr(self, "submit_exam"):
                try:
                    self.submit_exam()
                except Exception:
                    pass
            return

        # Tick again
        self._timer_after_id = self.after(1000, self.update_timer)

    # ---------- Submission flow ----------
    def confirm_submit(self):
        try:
            self.disable_all_buttons()
            self.save_current_answer()
            answer = messagebox.askyesno(
                "Review Answers",
                f"{self.student_name}, do you want to review your answers before final submission?"
            )
            if answer:
                self.show_review_answers()
            else:
                self.final_submit_confirmation()
            self.enable_all_buttons()
        except tk.TclError:
            pass

    # Review answers page (answered/unanswered only)
    def show_review_answers(self):
        self._bind_close_to_default()
        try:
            self.disable_all_buttons()
            self.clear_widgets()
            tk.Label(self, text=f"Review Answers for {self.student_name}", font=BASE_FONT_BOLD).pack(pady=10)

            canvas = tk.Canvas(self)
            scrollbar = tk.Scrollbar(self, orient="vertical", command=canvas.yview)
            scrollable_frame = tk.Frame(canvas)

            scrollable_frame.bind(
                "<Configure>",
                lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
            )

            canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
            canvas.configure(yscrollcommand=scrollbar.set)

            canvas.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="right", fill="y")

            q_list = self.questions.get(self.current_subject, [])
            for i, q in enumerate(q_list):
                user_ans = self.answers[self.current_subject][i]
                status = "Answered" if user_ans else "Unanswered"
                ans_text = f"Your answer: {user_ans if user_ans else 'Not answered'}"

                frame = tk.Frame(scrollable_frame, pady=5, padx=10, bg="#e0f7fa")
                frame.pack(fill="x", pady=2, padx=10)

                tk.Label(frame, text=f"Q{i+1}: {q.get('question')}", font=BASE_FONT_BOLD, wraplength=700,
                         justify="left", bg="#e0f7fa").pack(anchor="w")
                tk.Label(frame, text=ans_text, font=BASE_FONT, fg="blue", bg="#e0f7fa").pack(anchor="w", padx=10)
                tk.Label(frame, text=f"Status: {status}", font=BASE_FONT_BOLD,
                         fg="green" if status == "Answered" else "red", bg="#e0f7fa").pack(anchor="w", padx=10)

                btn_text = f"Go to Question {i+1}"
                btn = tk.Button(scrollable_frame, text=btn_text, font=BASE_FONT,
                                command=lambda i=i: self.go_to_question_from_review(i))
                btn.pack(fill="x", pady=2)

            btn_frame = tk.Frame(self)
            btn_frame.pack(pady=20)

            tk.Button(btn_frame, text="Confirm Final Submit", font=BASE_FONT, command=self.final_submit_confirmation).pack(side="left", padx=10)
            tk.Button(btn_frame, text="Return to Exam", font=BASE_FONT, command=self.show_exam_window).pack(side="left", padx=10)
            self.enable_all_buttons()
        except tk.TclError:
            pass

    def go_to_question_from_review(self, index):
        try:
            self.disable_all_buttons()
            self.save_current_answer()
            self.current_question_index = index
            self.clear_widgets()
            self.show_exam_window()
            self.load_question(index)
            self.enable_all_buttons()
        except tk.TclError:
            pass

    def final_submit_confirmation(self):
        try:
            self.disable_all_buttons()
            name = self.student_name
            if messagebox.askyesno("Final Confirmation", f"{name}, are you sure you want to submit your exam now?"):
                self.submit_exam()
            else:
                self.enable_all_buttons()
        except tk.TclError:
            pass

    # ---------- Exam submission and results ----------
    def submit_exam(self):
        try:
            self.save_current_answer()
            if self.timer_id:
                self.after_cancel(self.timer_id)
                self.timer_id = None

            q_list = self.questions.get(self.current_subject, [])
            total = len(q_list)
            attempted = sum(1 for ans in self.answers[self.current_subject] if ans)
            correct = sum(1 for i, ans in enumerate(self.answers[self.current_subject]) if ans == q_list[i].get("correct"))
            wrong = attempted - correct
            score_pct = (correct / total) * 100 if total > 0 else 0

            self.show_results(total, attempted, correct, wrong, score_pct)
        except tk.TclError:
            pass

    def export_results_to_pdf(self, total, attempted, correct, wrong, score_pct):
        """
        Export the current result summary to a PDF and open it.
        Safe against None/NaN/str scores and ensures message is always defined.
        """
        # --- imports local to the method to avoid module-level issues ---
        import math
        import textwrap
        import tempfile
        import webbrowser
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter

        # --- normalize inputs ---
        # Coerce score to float and clamp to [0, 100]
        try:
            score = float(score_pct)
            if math.isnan(score):
                score = 0.0
        except Exception:
            score = 0.0
        score = max(0.0, min(100.0, score))

        # Fallbacks for display fields
        student_name = getattr(self, "student_name", "") or "Candidate"
        subject = getattr(self, "current_subject", "") or "N/A"

        # --- decide message (no gaps; all decimals covered) ---
        if score >= 91:
            msg = ("Congratulations, you are a CBT “Champion”\n"
                   "Outstanding mastery and excellence—keep raising the bar!")
        elif 81 <= score < 90:
            msg = ("Congratulations, you are a CBT “Trailblazer”\n"
                   "Great performance—the path to mastery is clear!")
        elif 76 <= score < 80:
            msg = ("Congratulations, you are a CBT “Legend”\n"
                   "You’ve demonstrated mastery and excellence. Keep setting the pace!")
        elif 71 <= score < 75:
            msg = ("Great job! You are a CBT “Pathfinder”\n"
                   "Very good showing—push a bit more to enter Legend territory!")
        elif 66 <= score < 70:
            msg = ("Well done! You are a CBT “Master”\n"
                   "You’ve done really well. You’re steps away from Champion status!")
        elif 61 <= score < 65:
            msg = ("Good effort! You are a CBT “Achiever”\n"
                   "You’re doing good. With a bit more push, greatness is within reach!")
        elif 56 <= score < 60:
            msg = ("Keep going! You are a CBT “Striver”\n"
                   "You’re on the path. Keep working hard—improvement is inevitable!")
        elif 51 <= score < 55:
            msg = ("Don’t stop now! You are a CBT “Resilient Warrior”\n"
                   "You’ve shown effort. A little more consistency and you’ll soar!")
        else:
            msg = ("The journey has started! You are a CBT “Believer”\n"
                   "You’ve tried. You can do it. Don’t give up—greatness starts here!")

        msg += "\n\nMentor: Gbenga O. Olabode"

        # --- create PDF ---
        temp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        c = canvas.Canvas(temp_pdf.name, pagesize=letter)
        width, height = letter

        left_margin = 50
        right_margin = 50
        top_margin = 50
        bottom_margin = 40
        line_height = 20
        y = height - top_margin

        # Title
        c.setFont("Helvetica-Bold", 20)
        c.drawString(left_margin, y, f"Exam Results for {student_name}")
        y -= 40

        # Details
        c.setFont("Helvetica", 14)
        details = [
            f"Name of Candidate: {student_name}",
            f"Subject Attempted: {subject}",
            f"Total Questions: {total}",
            f"Attempted: {attempted}",
            f"Correct: {correct}",
            f"Wrong: {wrong}",
            f"Score: {score:.2f}%",
        ]
        for line in details:
            if y < bottom_margin:
                c.showPage(); c.setFont("Helvetica", 14); y = height - top_margin
            c.drawString(left_margin, y, line)
            y -= line_height

        # Section heading
        if y < bottom_margin + 30:
            c.showPage(); y = height - top_margin
        c.setFont("Helvetica-Bold", 16)
        c.drawString(left_margin, y, "Coach’s Message")
        y -= 25

        # Wrapped message
        import textwrap as _tw
        c.setFont("Helvetica", 12)
        usable_width = width - left_margin - right_margin

        def draw_wrapped(text, y_pos):
            # Wrap to approx. character width that fits usable_width (empirical 90)
            for paragraph in text.split("\n"):
                wrapped = _tw.wrap(paragraph, width=90) or [""]
                for line in wrapped:
                    if y_pos < bottom_margin:
                        c.showPage()
                        c.setFont("Helvetica", 12)
                        y_pos = height - top_margin
                    c.drawString(left_margin, y_pos, line)
                    y_pos -= line_height
                y_pos -= 5  # small space between paragraphs
            return y_pos

        y = draw_wrapped(msg, y)

        # Footer
        if y < bottom_margin:
            c.showPage()
            y = height - top_margin
        c.setFont("Helvetica-Oblique", 10)
        c.drawString(left_margin, bottom_margin - 10, "Generated by GO CBT App")

        c.save()

        # Open the PDF
        try:
            webbrowser.open(temp_pdf.name)
        except Exception:
            pass

        return temp_pdf.name

    def show_results(self, total, attempted, correct, wrong, score_pct):
        # Bind CLOSE (X) to outro only while Results screen is visible
        self._bind_close_x_to(self.on_result_exit)

        self.clear_widgets()

        # Title
        tk.Label(self, text=f"Exam Results for {self.student_name}",
                 font=("Arial", 20, "bold"), fg="green").pack(pady=20)

        # Table frame
        table_frame = tk.Frame(self, bg="white", bd=4, relief="solid",
                               highlightbackground="green", highlightthickness=4)
        table_frame.pack(pady=10, padx=20, fill="x")

        # Prepare mentor comment text
        mentor_comment = self.get_mentor_comment(score_pct)

        # Data rows
        data = [
            ("Name of Candidate:", self.student_name),
            ("Subject Attempted:", self.current_subject),
            ("Total Questions:", str(total)),
            ("Attempted:", str(attempted)),
            ("Correct:", str(correct)),
            ("Wrong:", str(wrong)),
            ("Score (%):", f"{score_pct:.2f}"),
            ("Mentor's Comment:", mentor_comment),
            ("Mentor:", "Gbenga O. Olabode"),
        ]

        for row_idx, (label_text, value_text) in enumerate(data):
            left_lbl = tk.Label(table_frame, text=label_text, font=("Arial", 16, "bold"),
                                fg="green", bg="white", borderwidth=1, relief="solid",
                                anchor="w", padx=10, pady=5)
            left_lbl.grid(row=row_idx, column=0, sticky="ew", padx=1, pady=1)

            right_lbl = tk.Label(table_frame, text=value_text, font=("Arial", 16),
                                 fg="green", bg="white", borderwidth=1, relief="solid",
                                 anchor="w", padx=10, pady=5, justify="left", wraplength=750)
            right_lbl.grid(row=row_idx, column=1, sticky="ew", padx=1, pady=1)

        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_columnconfigure(1, weight=2)

        # Buttons (including Exit -> outro)
        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=20)

        tk.Button(btn_frame, text="Review Answers", font=("Arial", 16),
                  command=self.show_score_details).pack(side="left", padx=10)

        tk.Button(btn_frame, text="Save/Print Results as PDF", font=("Arial", 16),
                  command=lambda: self.export_results_to_pdf(
                      total, attempted, correct, wrong, score_pct
                  )).pack(side="left", padx=10)

        tk.Button(btn_frame, text="Restart Exam", font=("Arial", 16),
                  command=self.restart_exam).pack(side="left", padx=10)

        # Exit should show the Goodbye/Thank-you screen (outro)
        tk.Button(btn_frame, text="Exit", font=("Arial", 16),
                  command=self.on_result_exit).pack(side="left", padx=10)

    def on_result_exit(self):
        """Public hook: when user clicks 'Exit' or Close X on the Results screen."""
        self.show_goodbye_and_exit()

    def show_goodbye_and_exit(self):
        """Show branded outro (logo + thank-you GIF + message), then close app."""
        # While outro is visible, CLOSE (X) should simply close immediately to avoid loops
        self._bind_close_x_to(self.master.destroy)

        self.clear_widgets()

        # Build and pack the goodbye screen; auto-closes in ~4s, or user can 'Exit Now'
        goodbye = GoodbyeScreen(self, on_exit=self.master.destroy, auto_close_ms=4000)
        goodbye.pack(fill="both", expand=True)

    def get_mentor_comment(self, score_pct: float) -> str:
        if score_pct >= 91:
            return ("Congratulations, you are a CBT “Champion”\n"
                    "Outstanding mastery and excellence—keep raising the bar!")
        elif 81 <= score_pct < 90:
            return ("Congratulations, you are a CBT “Trailblazer”\n"
                    "Great performance—the path to mastery is clear!")
        elif 76 <= score_pct < 80:
            return ("Congratulations, you are a CBT “Legend”\n"
                    "You’ve demonstrated mastery and excellence. Keep setting the pace!")
        elif 71 <= score_pct < 75:
            return ("Great job! You are a CBT “Pathfinder”\n"
                    "Very good showing—push a bit more to enter Legend territory!")
        elif 66 <= score_pct < 70:
            return ("Well done! You are a CBT “Master”\n"
                    "You’ve done really well. You’re steps away from Champion status!")
        elif 61 <= score_pct < 65:
            return ("Good effort! You are a CBT “Achiever”\n"
                    "You’re doing good. With a bit more push, greatness is within reach!")
        elif 56 <= score_pct < 60:
            return ("Keep going! You are a CBT “Striver”\n"
                    "You’re on the path. Keep working hard—improvement is inevitable!")
        elif 51 <= score_pct < 55:
            return ("Don’t stop now! You are a CBT “Resilient Warrior”\n"
                    "You’ve shown effort. A little more consistency and you’ll soar!")
        else:
            return ("The journey has started! You are a CBT “Believer”\n"
                    "You’ve tried. You can do it. Don’t give up—greatness starts here!")

    def show_score_details(self):
        self._bind_close_to_default()
        self.clear_widgets()
        tk.Label(self,
                 text=f"Detailed Results for {self.student_name}",
                 font=BASE_FONT_BOLD).pack(pady=10)

        # Scrollable container
        container = tk.Frame(self)
        container.pack(fill="both", expand=True)

        canvas = tk.Canvas(container)
        vscroll = tk.Scrollbar(container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vscroll.set)

        vscroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        table = tk.Frame(canvas)
        canvas.create_window((0, 0), window=table, anchor="nw")

        def on_configure(event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
        table.bind("<Configure>", lambda e: on_configure())

        # Styles
        header_style = dict(font=("Arial", 14, "bold"),
                            bg="#e8f5e9", fg="#1b5e20",
                            borderwidth=1, relief="solid",
                            anchor="w", padx=8, pady=6)

        # NOTE: no 'fg' here; we set it per cell
        body_style   = dict(font=("Arial", 12),
                            bg="white",
                            borderwidth=1, relief="solid",
                            anchor="w", padx=8, pady=6)
        base_fg = "#1b5e20"

        # Header row
        headers = ["Question", "Your Answer", "Correct answer", "Correct answer text", "Status"]
        for col, title in enumerate(headers):
            tk.Label(table, text=title, **header_style).grid(row=0, column=col, sticky="nsew")

        # Column sizing
        table.grid_columnconfigure(0, weight=5)  # Question
        table.grid_columnconfigure(1, weight=1)  # Your Answer
        table.grid_columnconfigure(2, weight=1)  # Correct letter
        table.grid_columnconfigure(3, weight=4)  # Correct text
        table.grid_columnconfigure(4, weight=1)  # Status

        # Populate rows
        q_list = self.questions.get(self.current_subject, [])
        answers = self.answers.get(self.current_subject, [])

        for idx, q in enumerate(q_list, start=1):
            q_text = q.get("question", "")
            options = q.get("options", {}) or {}
            correct_letter = (q.get("correct") or "").strip()
            correct_text = options.get(correct_letter, "")
            user_letter = ((answers[idx-1] or "").strip()) if idx-1 < len(answers) else ""

            if not user_letter:
                status_text = "Unanswered"
                status_fg = "#616161"  # gray
            elif user_letter == correct_letter:
                status_text = "Correct"
                status_fg = "#1b5e20"  # green
            else:
                status_text = "Incorrect"
                status_fg = "#b71c1c"  # red

            # Cells (set fg explicitly)
            tk.Label(table, text=f"{idx}. {q_text}", wraplength=750, justify="left",
                     fg=base_fg, **body_style).grid(row=idx, column=0, sticky="nsew")
            tk.Label(table, text=(user_letter or "—"),
                     fg=base_fg, **body_style).grid(row=idx, column=1, sticky="nsew")
            tk.Label(table, text=(correct_letter or "—"),
                     fg=base_fg, **body_style).grid(row=idx, column=2, sticky="nsew")
            tk.Label(table, text=(correct_text or "—"), wraplength=550, justify="left",
                     fg=base_fg, **body_style).grid(row=idx, column=3, sticky="nsew")
            tk.Label(table, text=status_text,
                     fg=status_fg, **body_style).grid(row=idx, column=4, sticky="nsew")

        # Buttons
        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=12)

        tk.Button(btn_frame, text="Save Detailed Results as PDF", font=BASE_FONT,
                  command=self.export_detailed_results_to_pdf).pack(side="left", padx=10)

        # Recompute summary for "Back to Results"
        total = len(q_list)
        attempted = sum(1 for a in answers if a)
        correct = sum(1 for i, a in enumerate(answers) if a and a == q_list[i].get("correct"))
        wrong = attempted - correct
        score_pct = (correct / total * 100) if total else 0.0

        tk.Button(btn_frame, text="Back to Results", font=BASE_FONT,
                  command=lambda: self.show_results(total, attempted, correct, wrong, score_pct))\
          .pack(side="left", padx=10)

    def export_detailed_results_to_pdf(self):
        """
        Save a detailed results PDF with columns:
        Question | Your Answer | Correct answer | Correct answer text | Status
        Includes logo (assets/logo.png) if present, writes to ~/Documents with a
        timestamped filename, sets PDF metadata, opens the file and shows it in Explorer.
        """
        import os, pathlib, datetime, subprocess
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.utils import ImageReader
        from reportlab.lib import colors

        # ---- Gather data ----
        student_name = (getattr(self, "student_name", "") or "Candidate").strip()
        subject = (getattr(self, "current_subject", "") or "Results").strip()
        q_list = self.questions.get(self.current_subject, [])
        answers = self.answers.get(self.current_subject, [])

        # ---- Output path (Documents, timestamped) ----
        docs = pathlib.Path.home() / "Documents"
        docs.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        safe_name = "".join(ch for ch in student_name if ch.isalnum() or ch in " _-").strip() or "Candidate"
        safe_subject = "".join(ch for ch in subject if ch.isalnum() or ch in " _-").strip() or "Results"
        out_path = docs / f"GO_CBT_Detailed_{safe_name}_{safe_subject}_{ts}.pdf"

        # ---- Canvas & metadata ----
        c = canvas.Canvas(str(out_path), pagesize=letter)
        width, height = letter
        c.setAuthor("GO CBT App")
        c.setTitle(f"Detailed Results - {safe_name}")
        c.setSubject(safe_subject)
        c.setCreator("GO CBT App")

        # ---- Layout constants ----
        left_margin   = 40
        right_margin  = 40
        top_margin    = 60
        bottom_margin = 40
        y             = height - top_margin

        # Table fonts & sizes
        header_font = "Helvetica-Bold"
        body_font   = "Helvetica"
        title_font  = "Helvetica-Bold"
        title_size  = 18
        header_size = 11
        body_size   = 10
        line_gap    = 14   # line height for wrapped text
        cell_pad_v  = 4    # vertical padding per cell
        cell_pad_h  = 4    # horizontal padding per cell

        # Column widths (must sum to usable width)
        usable_width = width - left_margin - right_margin  # 612 - 80 = 532
        col_w = {
            "question": 220,    # question text (will wrap)
            "your_ans":  60,    # letter
            "correct":   60,    # letter
            "corr_txt":  162,   # correct option text (wrap)
            "status":    30,    # short status ('✓','✗','—') + word
        }
        assert sum(col_w.values()) == int(usable_width), "Column widths must sum to usable width"

        # ---- Optional logo ----
        try:
            logo_path = resource_path("assets", "logo.png")
            if os.path.exists(logo_path):
                img = ImageReader(logo_path)
                iw, ih = img.getSize()
                target_w = 110
                target_h = int(ih * (target_w / iw)) if iw else 0
                x = (width - target_w) / 2
                c.drawImage(img, x, y - target_h, width=target_w, height=target_h, mask="auto")
                y -= target_h + 8
        except Exception:
            pass

        # ---- Title ----
        c.setFont(title_font, title_size)
        c.drawCentredString(width / 2, y, f"Detailed Results for {student_name}")
        y -= 20
        c.setFont(body_font, 11)
        c.drawCentredString(width / 2, y, f"Subject: {subject}")
        y -= 24

        # --- Header row drawer (reused on new pages) ---
        def draw_header(y_top):
            c.setFillColor(colors.HexColor("#e8f5e9"))
            c.rect(left_margin, y_top - (line_gap + 2*cell_pad_v),
                   usable_width, (line_gap + 2*cell_pad_v), fill=1, stroke=0)
            c.setFillColor(colors.black)
            c.setFont(header_font, header_size)

            x = left_margin
            headers = [
                ("Question", col_w["question"]),
                ("Your Answer", col_w["your_ans"]),
                ("Correct answer", col_w["correct"]),
                ("Correct answer text", col_w["corr_txt"]),
                ("Status", col_w["status"]),
            ]
            for text, w in headers:
                c.drawString(x + cell_pad_h, y_top - cell_pad_v - (line_gap - header_size) / 2 - header_size, text)
                x += w
            # bottom y of header row
            return y_top - (line_gap + 2*cell_pad_v)

        # --- Text wrapper using canvas metrics ---
        def wrap_text(t, max_w, font_name, font_size):
            """Wrap text to lines that fit within max_w (pt) using canvas metrics."""
            if not t:
                return [""]
            c.setFont(font_name, font_size)
            lines = []
            for para in str(t).split("\n"):
                words = para.split()
                if not words:
                    lines.append("")
                    continue
                cur = words[0]
                for w in words[1:]:
                    if c.stringWidth(cur + " " + w, font_name, font_size) <= max_w - 2*cell_pad_h:
                        cur += " " + w
                    else:
                        lines.append(cur)
                        cur = w
                lines.append(cur)
            return lines

        # --- Draw one data row (with wrapping, borders, colors) ---
        def draw_row(y_top, row_data):
            # row_data keys: question, your_ans, correct, corr_txt, status_text, status_color
            q_lines   = wrap_text(row_data["question"], col_w["question"], body_font, body_size)
            ua_lines  = wrap_text(row_data["your_ans"], col_w["your_ans"], body_font, body_size)
            ca_lines  = wrap_text(row_data["correct"], col_w["correct"], body_font, body_size)
            ct_lines  = wrap_text(row_data["corr_txt"], col_w["corr_txt"], body_font, body_size)
            st_lines  = wrap_text(row_data["status_text"], col_w["status"], body_font, body_size)

            max_lines = max(len(q_lines), len(ua_lines), len(ca_lines), len(ct_lines), len(st_lines))
            row_h = max_lines * line_gap + 2*cell_pad_v

            # Page break?
            if y_top - row_h < bottom_margin:
                c.showPage()
                # re-draw page header (logo optional omitted for inner pages for speed)
                y_new = height - top_margin
                c.setFont(title_font, title_size)
                c.drawCentredString(width / 2, y_new, f"Detailed Results for {student_name}")
                y_new -= 20
                c.setFont(body_font, 11)
                c.drawCentredString(width / 2, y_new, f"Subject: {subject}")
                y_new -= 24
                # header row on new page
                y_after_header = draw_header(y_new)
                y_top = y_after_header

            # Draw cell borders & texts
            c.setFont(body_font, body_size)
            x = left_margin
            # Background (white)
            c.setFillColor(colors.white)
            c.rect(left_margin, y_top - row_h, usable_width, row_h, fill=1, stroke=0)

            # Column: Question
            c.setFillColor(colors.black)
            c.rect(x, y_top - row_h, col_w["question"], row_h, fill=0, stroke=1)
            yy = y_top - cell_pad_v - body_size
            for line in q_lines:
                c.drawString(x + cell_pad_h, yy, line)
                yy -= line_gap
            x += col_w["question"]

            # Column: Your Answer
            c.rect(x, y_top - row_h, col_w["your_ans"], row_h, fill=0, stroke=1)
            yy = y_top - cell_pad_v - body_size
            for line in ua_lines:
                c.drawString(x + cell_pad_h, yy, line)
                yy -= line_gap
            x += col_w["your_ans"]

            # Column: Correct answer (letter)
            c.rect(x, y_top - row_h, col_w["correct"], row_h, fill=0, stroke=1)
            yy = y_top - cell_pad_v - body_size
            for line in ca_lines:
                c.drawString(x + cell_pad_h, yy, line)
                yy -= line_gap
            x += col_w["correct"]

            # Column: Correct answer text
            c.rect(x, y_top - row_h, col_w["corr_txt"], row_h, fill=0, stroke=1)
            yy = y_top - cell_pad_v - body_size
            for line in ct_lines:
                c.drawString(x + cell_pad_h, yy, line)
                yy -= line_gap
            x += col_w["corr_txt"]

            # Column: Status (color-coded ✓/✗/— plus word)
            c.rect(x, y_top - row_h, col_w["status"], row_h, fill=0, stroke=1)
            yy = y_top - cell_pad_v - body_size
            c.setFillColor(row_data["status_color"])
            for line in st_lines:
                c.drawString(x + cell_pad_h, yy, line)
                yy -= line_gap

            # bottom y of row
            return y_top - row_h

        # ---- Draw table header first ----
        y = draw_header(y)

        # ---- Iterate rows ----
        for i, q in enumerate(q_list, start=1):
            q_text = f"{i}. {q.get('question', '')}"
            options = q.get("options", {}) or {}
            correct_letter = (q.get("correct") or "").strip()
            correct_text   = options.get(correct_letter, "") or ""
            user_letter    = (answers[i-1].strip() if (i-1) < len(answers) and answers[i-1] else "")

            if not user_letter:
                status_text = "— Unanswered"
                status_color = colors.HexColor("#616161")  # gray
            elif user_letter == correct_letter:
                status_text = "✓ Correct"
                status_color = colors.HexColor("#1b5e20")  # green
            else:
                status_text = "✗ Incorrect"
                status_color = colors.HexColor("#b71c1c")  # red

            row = {
                "question":    q_text,
                "your_ans":    user_letter or "—",
                "correct":     correct_letter or "—",
                "corr_txt":    correct_text or "—",
                "status_text": status_text,
                "status_color": status_color,
            }
            y = draw_row(y, row)

        # ---- Footer / finalize ----
        c.setFillColor(colors.black)
        if y < bottom_margin:
            c.showPage()
            y = height - top_margin
        c.setFont("Helvetica-Oblique", 10)
        c.drawString(left_margin, bottom_margin - 10, "Generated by GO CBT App")
        c.save()

        # ---- Open PDF and show in Explorer ----
        try:
            if os.name == "nt":
                os.startfile(str(out_path))  # open the PDF
                try:
                    subprocess.run(["explorer", "/select,", str(out_path)], check=False)
                except Exception:
                    pass
            else:
                import webbrowser
                webbrowser.open(out_path.as_uri())
        except Exception:
            pass

        return str(out_path)

    def restart_exam(self):
        self._bind_close_to_default()
        self.current_question_index = 0
        self.answers[self.current_subject] = [None] * len(self.questions[self.current_subject])
        self.show_subject_selection()

if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("1024x768")
    app = GO_CBT_App(master=root)
    app.show_login_page()
    root.mainloop()
