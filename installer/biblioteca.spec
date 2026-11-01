# Ricetta PyInstaller: una cartella "Biblioteca" con Biblioteca.exe, per chi non ha Python.
# PyMuPDF (AGPL) e' nell'ambiente di sviluppo ma NON deve entrare nel programma: e' escluso qui
# e build.ps1 controlla che non ci sia.
import os

QUI = os.path.abspath(SPECPATH)
BASE = os.path.dirname(QUI)

a = Analysis(
    [os.path.join(BASE, "Biblioteca.pyw")],
    pathex=[BASE],
    datas=[(os.path.join(BASE, "biblioteca", "risorse"), os.path.join("biblioteca", "risorse"))],
    hiddenimports=["webview.platforms.edgechromium", "webview.platforms.winforms", "clr",
                   "sklearn.feature_extraction", "sklearn.linear_model", "sklearn.pipeline"],
    excludes=["fitz", "pymupdf", "PyMuPDF", "tkinter", "matplotlib", "pytest", "IPython", "pandas", "PyInstaller"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Biblioteca", console=False,
          icon=os.path.join(QUI, "biblioteca.ico"), version=os.path.join(QUI, "versione.txt"))
coll = COLLECT(exe, a.binaries, a.datas, name="Biblioteca")
