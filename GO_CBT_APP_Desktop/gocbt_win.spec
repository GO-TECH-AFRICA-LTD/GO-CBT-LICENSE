# gocbt_win.spec — GO CBT App (Windows, PyInstaller 6.x)
# - GUI app (no console)
# - Bundles whole assets/ tree at COLLECT stage
# - Safe datas format (tuples only) to avoid "too many values to unpack"
# - Hiddenimports for tkinter, Pillow, and requests stack

import os
from PyInstaller.building.build_main import Analysis, PYZ, EXE, COLLECT
from PyInstaller.building.datastruct import Tree
from PyInstaller.utils.hooks import collect_submodules

APP_NAME = "GO_CBT_App"

# -------- icon (optional) --------
ICON_CANDIDATES = [
    os.path.join("assets", "app.ico"),
    os.path.join("assets", "go_cbt_logo.ico"),
    "app.ico",
]
def first_exists(paths):
    for p in paths:
        if os.path.isfile(p):
            return p
    return None

# -------- datas (ONLY tuples here) --------
datas = []
# include optional text/md files if you have them (safe to keep even if absent)
for p in ("splash_content.md", "splash_content.txt"):
    if os.path.isfile(p):
        datas.append((p, "."))  # (src, dest)

# -------- hidden imports --------
hidden = set()
# Tk / ttk
hidden.update(["tkinter", "tkinter.ttk"])
# Pillow core and common submodules
hidden.update(["PIL", "PIL.Image", "PIL.ImageTk"])
# Requests stack (and its submodules)
hidden.update(collect_submodules("requests"))
hidden.update(["certifi", "charset_normalizer", "idna", "urllib3"])

# -------- analysis --------
a = Analysis(
    ["main.py"],            # entry
    pathex=["."],
    binaries=[],
    datas=datas,            # tuples only!
    hiddenimports=list(hidden),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # GUI app
    icon=first_exists(ICON_CANDIDATES),
)

# -------- collect (add assets tree here) --------
collect_args = [exe, a.binaries, a.zipfiles, a.datas]
if os.path.isdir("assets"):
    # bundles everything under assets/ → dist/GO_CBT_App/assets/...
    collect_args.append(Tree("assets", prefix="assets"))

coll = COLLECT(
    *collect_args,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)
