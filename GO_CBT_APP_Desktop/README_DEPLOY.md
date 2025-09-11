# GO CBT APP — Desktop Client (Release Bundle)
Files:
- main.py
- activation_dialog.py
- student_portal.py  (your merged file retained)
- splash_screen.py
- license_client.py
- path_utils.py
- GO_CBT_APP_PROD.spec
Build:
  rmdir /s /q build dist 2>nul
  pyinstaller GO_CBT_APP_PROD.spec
Server env (once):
  setx GOCBT_SERVER "https://go-cbt-license.onrender.com"
