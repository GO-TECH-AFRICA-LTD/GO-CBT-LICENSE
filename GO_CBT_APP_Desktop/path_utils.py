import os, sys

def _base_dir() -> str:
    if hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

BASE_DIR = _base_dir()

def resource_path(*parts: str) -> str:
    return os.path.join(BASE_DIR, *parts)

def assets_dir_candidates() -> list[str]:
    candidates = []
    candidates.append(os.path.join(BASE_DIR, "assets"))
    candidates.append(os.path.join(BASE_DIR, "_internal", "assets"))
    candidates.append(os.path.join(os.path.dirname(BASE_DIR), "assets"))

    cur = BASE_DIR
    for _ in range(5):
        if os.path.basename(cur).lower() == "go_cbt_app":
            candidates.append(os.path.join(cur, "assets"))
            break
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent

    if hasattr(sys, "_MEIPASS"):
        candidates.append(os.path.join(sys._MEIPASS, "assets"))

    seen, unique = set(), []
    for d in candidates:
        d = os.path.normpath(d)
        if d not in seen:
            seen.add(d)
            unique.append(d)
    return unique

def asset_path(*parts: str) -> str:
    for d in assets_dir_candidates():
        p = os.path.join(d, *parts)
        if os.path.exists(p):
            return p
    return os.path.join(assets_dir_candidates()[0], *parts)

def find_app_icon() -> str | None:
    for d in assets_dir_candidates():
        for name in ("new_app_icon.ico", "go_cbt.ico"):
            p = os.path.join(d, name)
            if os.path.exists(p):
                return p
    return None
