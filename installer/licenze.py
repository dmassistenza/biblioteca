"""Scrive LICENZE.txt per il programma distribuito: ogni libreria Python davvero inclusa nel pacchetto
(cartelle *.dist-info dentro _internal) con la sua licenza, piu' i componenti esterni.
Si ferma con un errore se trova una licenza AGPL o GPL senza eccezione: il programma non sarebbe distribuibile.
Uso: python licenze.py <cartella dist\\Biblioteca> <cartella build\\biblioteca>
"""
import glob
import os
import re
import sys

ESTERNI = [
    ("Python", "PSF License", "https://docs.python.org/3/license.html"),
    ("llama.cpp (motore dell'AI sul PC)", "MIT", "llama\\LICENSE-llama.cpp.txt"),
    ("LLVM OpenMP (usato da llama.cpp)", "Apache-2.0 WITH LLVM-exception", "llama\\LICENSE-LLVM-OpenMP"),
    ("Modelli Qwen3.5 2B e 4B (scaricati a parte, non inclusi)", "Apache-2.0", "https://huggingface.co/Qwen"),
    ("Microsoft Edge WebView2 (componente di Windows, non incluso)", "Microsoft", "https://developer.microsoft.com/microsoft-edge/webview2/"),
    ("PyInstaller (bootloader)", "GPL-2.0 con eccezione per i programmi creati", "https://pyinstaller.org/en/stable/license.html"),
]
# librerie che non dichiarano la licenza nei metadati (verificata sul loro sito)
NOTE = {"clr_loader": "MIT (progetto pythonnet)"}
VIETATE = re.compile(r"\bA?GPL\b|GNU (Affero )?General Public", re.I)
ECCEZIONI = re.compile(r"LGPL|exception|Lesser", re.I)


def licenza(meta):
    for k in ("License-Expression", "License"):
        v = (meta.get(k) or "").strip()
        if v and len(v) < 120 and v.upper() != "UNKNOWN":
            return v.splitlines()[0]
    cl = [c.split("::")[-1].strip() for c in meta.get_all("Classifier") or [] if c.startswith("License ::")]
    return ", ".join(cl) or "vedi il pacchetto"


def moduli_inclusi(build):
    """Nomi di primo livello dei moduli Python messi nel pacchetto (dal sommario PYZ-00.toc di PyInstaller)."""
    import ast
    with open(os.path.join(build, "PYZ-00.toc"), encoding="utf-8") as f:
        toc = ast.literal_eval(f.read())
    return {voce[0].split(".")[0] for voce in toc[1]}


def main(dist, build):
    """Gira con il Python dell'ambiente di sviluppo: da li' legge i metadati delle librerie incluse."""
    from importlib import metadata
    righe, problemi = [], []
    per_modulo = metadata.packages_distributions()
    nomi = sorted({d for m in moduli_inclusi(build) for d in per_modulo.get(m, [])}, key=str.lower)
    for nome in nomi:
        meta = metadata.metadata(nome)
        ver, lic = meta.get("Version"), NOTE.get(nome) or licenza(meta)
        if nome.lower() in ("pyinstaller", "pip", "setuptools"):
            continue
        righe.append(f"{nome} {ver} - {lic}")
        if VIETATE.search(lic) and not ECCEZIONI.search(lic):
            problemi.append(f"{nome}: {lic}")
    if glob.glob(os.path.join(dist, "_internal", "fitz*")) or glob.glob(os.path.join(dist, "_internal", "pymupdf*")):
        problemi.append("PyMuPDF (AGPL) e' finito nel pacchetto")
    testo = ["Biblioteca - componenti e licenze", "=" * 40, "",
             "Il programma usa solo componenti con licenza libera che ne permette la distribuzione.", "",
             "Librerie Python incluse:"] + [f"  {r}" for r in righe] + ["", "Altri componenti:"] + \
            [f"  {n} - {l} ({u})" for n, l, u in ESTERNI] + ["", "I testi completi delle licenze sono nelle cartelle",
                                                             "_internal\\*.dist-info e llama\\ dentro la cartella del programma."]
    with open(os.path.join(dist, "LICENZE.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(testo) + "\n")
    print(f"{len(righe)} librerie scritte in LICENZE.txt")
    if problemi:
        print("LICENZE NON AMMESSE:", *problemi, sep="\n  ")
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
