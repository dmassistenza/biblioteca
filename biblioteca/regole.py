"""Regole di sicurezza comuni: cartelle ammesse e protette, nomi di file validi, percorsi lunghi."""
import os
import re

MAX_PATH = 250
ILLEGALI = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
NON_LIBRI = {"desktop.ini", "thumbs.db", ".ds_store"}
EBOOK = (".pdf", ".epub", ".mobi", ".azw3", ".azw", ".fb2")


def dentro(p, radici):
    p = os.path.normcase(os.path.abspath(p))
    for r in radici:
        r = os.path.normcase(os.path.abspath(r))
        if p == r or p.startswith(r.rstrip("\\/") + os.sep):
            return True
    return False


def lungo(p):
    """Prefisso \\\\?\\ per i percorsi oltre i 240 caratteri (Windows)."""
    p = os.path.abspath(p)
    return p if p.startswith("\\\\?\\") or len(p) < 240 else "\\\\?\\" + p


def nome_sicuro(s):
    s = ILLEGALI.sub("", (s or "").replace(":", ","))
    return re.sub(r"\s+", " ", s).strip().rstrip(".")


def percorri(radice, escluse=()):
    """Tutti i file sotto radice, saltando le cartelle escluse (protette, Biblioteca, _duplicati...)."""
    for dp, dirs, fns in os.walk(radice):
        dirs[:] = sorted(d for d in dirs if not dentro(os.path.join(dp, d), escluse))
        for fn in sorted(fns):
            yield os.path.join(dp, fn)
