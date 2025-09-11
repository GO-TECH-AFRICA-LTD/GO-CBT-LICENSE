# GO_CBT_APP_PROD.spec — production (GUI), safe datas
import os, glob
from PyInstaller.utils.hooks import collect_submodules
hidden = []
try: hidden += collect_submodules('requests')
except Exception: pass
block_cipher = None
def add_if_exists(datas_list, src, dst):
    if os.path.exists(src): datas_list.append((src, dst))
def add_glob(datas_list, pattern, dst):
    for p in glob.glob(pattern): datas_list.append((p, dst))
datas = []
for core in ('student_portal.py','license_client.py','activation_dialog.py','splash_screen.py','path_utils.py','gocbt_logo.png','app.ico'):
    add_if_exists(datas, core, '.')
add_glob(datas, os.path.join('assets','*.json'), 'assets')
for folder in ('images','media','fonts','static','data'):
    if os.path.isdir(folder): add_glob(datas, os.path.join(folder,'*.*'), folder)
for pattern in ('*.png','*.gif','*.jpg','*.jpeg','*.json','*.csv','*.txt'):
    add_glob(datas, pattern, '.')
a = Analysis(['main.py'], pathex=['.'], binaries=[], datas=datas, hiddenimports=hidden,
             hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], win_no_prefer_redirects=False,
             win_private_assemblies=False, cipher=block_cipher, noarchive=False)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [], name='GO_CBT_APP', debug=False,
          bootloader_ignore_signals=False, strip=False, upx=True, console=False,
          icon='app.ico' if os.path.exists('app.ico') else None)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, strip=False, upx=True, upx_exclude=[], name='GO_CBT_APP')
