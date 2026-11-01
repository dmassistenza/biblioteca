"""Chiavi delle AI conservate cifrate con Windows (DPAPI, legata all'utente di Windows):
un altro utente o un altro PC non puo' leggerle. Nel file c'e' solo il testo cifrato.
"""
import base64
import ctypes
import ctypes.wintypes as wt
import json
import os

from .impostazioni import cartella_app


class _BLOB(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(b):
    buf = ctypes.create_string_buffer(b, len(b))
    return _BLOB(len(b), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


def _cifra(testo):
    inp, _buf = _blob(testo.encode("utf-8"))
    out = _BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(inp), "Biblioteca", None, None, None, 0, ctypes.byref(out)):
        raise OSError("CryptProtectData non riuscita")
    try:
        return base64.b64encode(ctypes.string_at(out.pbData, out.cbData)).decode("ascii")
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def _decifra(b64):
    inp, _buf = _blob(base64.b64decode(b64))
    out = _BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(inp), None, None, None, None, 0, ctypes.byref(out)):
        raise OSError("CryptUnprotectData non riuscita")
    try:
        return ctypes.string_at(out.pbData, out.cbData).decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def _file():
    return os.path.join(cartella_app(), "chiavi.json")


def _tutte():
    try:
        with open(_file(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def salva(servizio, chiave):
    d = _tutte()
    d[servizio] = _cifra(chiave)
    tmp = _file() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f)
    os.replace(tmp, _file())


def leggi(servizio):
    v = _tutte().get(servizio)
    if not v:
        return ""
    try:
        return _decifra(v)
    except OSError:
        return ""


def togli(servizio):
    """Dimentica la chiave (si toglie la voce dal file delle chiavi: non e' un file dell'utente)."""
    d = _tutte()
    if d.pop(servizio, None) is not None:
        with open(_file(), "w", encoding="utf-8") as f:
            json.dump(d, f)


def mascherata(chiave):
    return (chiave[:4] + "…" + chiave[-4:]) if len(chiave) > 12 else ("•" * len(chiave))
