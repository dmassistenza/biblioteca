"""AI sul PC: llama.cpp (llama-server, licenza MIT) con un modello aperto Qwen3.5 (Apache 2.0).
Gratis, senza account e senza internet (internet serve solo per scaricare il modello, una volta;
in alternativa il modello si carica da un file, per esempio da una chiavetta USB).
- 4B (2,6 GB) se il PC ha almeno 8 GB di RAM, altrimenti 2B (1,2 GB): nella prova 78% e 56% di titoli giusti.
- La scheda video si usa solo se il modello ci sta tutto: a meta' e' piu' lenta del processore.
"""
import ctypes
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

MODELLI = {
    "4B": {"file": "Qwen3.5-4B-Q4_K_M.gguf", "url": "https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/main/Qwen3.5-4B-Q4_K_M.gguf",
           "mb": 2614, "ram_gb": 8},
    "2B": {"file": "Qwen3.5-2B-Q4_K_M.gguf", "url": "https://huggingface.co/unsloth/Qwen3.5-2B-GGUF/resolve/main/Qwen3.5-2B-Q4_K_M.gguf",
           "mb": 1222, "ram_gb": 4},
}
_processo = None


def ram_gb():
    class MS(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    m = MS()
    m.dwLength = ctypes.sizeof(MS)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.ullTotalPhys / 1024 ** 3


def consigliato():
    return "4B" if ram_gb() >= 7.5 else "2B"  # 8 GB nominali risultano un po' meno


def cartella_motore():
    """llama.cpp accanto al programma (installer) oppure indicato da BIBLIOTECA_LLAMA (prove)."""
    base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.dirname(__file__))
    for d in (os.environ.get("BIBLIOTECA_LLAMA", ""), os.path.join(base, "llama")):
        if d and os.path.isfile(os.path.join(d, "llama-server.exe")):
            return d
    return ""


def cartella_modelli(imp=None):
    d = (imp or {}).get("ai", {}).get("cartella_modelli") or os.path.join(
        os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "Biblioteca", "modelli")
    os.makedirs(d, exist_ok=True)
    return d


def presente(nome, imp=None):
    p = os.path.join(cartella_modelli(imp), MODELLI[nome]["file"])
    return p if os.path.isfile(p) and os.path.getsize(p) > MODELLI[nome]["mb"] * 1024 * 1024 * 0.95 else ""


def stato(imp=None):
    return {"motore": bool(cartella_motore()), "ram_gb": round(ram_gb(), 1), "consigliato": consigliato(),
            "modelli": {k: {"presente": bool(presente(k, imp)), "mb": v["mb"]} for k, v in MODELLI.items()},
            "attivo": _processo is not None and _processo.poll() is None}


def scarica(nome, avanzamento=None, stop=None, imp=None):
    """Scarica il modello in un file .part e lo rinomina solo a scaricamento finito.
    Se si interrompe, la volta dopo riprende da dove era arrivato."""
    m = MODELLI[nome]
    dest = os.path.join(cartella_modelli(imp), m["file"])
    part = dest + ".part"
    fatto = os.path.getsize(part) if os.path.exists(part) else 0
    req = urllib.request.Request(m["url"], headers={"Range": f"bytes={fatto}-"} if fatto else {})
    with urllib.request.urlopen(req, timeout=60) as r:
        if fatto and r.status != 206:  # il server non riprende: si ricomincia
            fatto = 0
        totale = fatto + int(r.headers.get("Content-Length", 0))
        with open(part, "ab" if fatto else "wb") as f:
            while True:
                if stop is not None and stop.is_set():
                    return {"interrotto": True, "fatto_mb": fatto // 2 ** 20}
                b = r.read(1 << 20)
                if not b:
                    break
                f.write(b)
                fatto += len(b)
                if avanzamento:
                    avanzamento(fatto // 2 ** 20, totale // 2 ** 20, m["file"])
    if totale and fatto != totale:
        raise OSError(f"scaricamento incompleto: {fatto} di {totale} byte")
    _controlla_gguf(part)
    os.replace(part, dest)
    return {"file": dest}


def _controlla_gguf(p):
    with open(p, "rb") as f:
        if f.read(4) != b"GGUF":
            raise ValueError("il file non è un modello GGUF")


def importa(path, imp=None):
    """Modello da un file (chiavetta USB, cartella condivisa): si COPIA nella cartella dei modelli."""
    _controlla_gguf(path)
    nome = next((k for k, v in MODELLI.items() if v["file"].lower() == os.path.basename(path).lower()), "")
    if not nome:
        raise ValueError("nome del file sconosciuto: servono " + " o ".join(v["file"] for v in MODELLI.values()))
    dest = os.path.join(cartella_modelli(imp), MODELLI[nome]["file"])
    if os.path.abspath(dest) != os.path.abspath(path):
        shutil.copyfile(path, dest + ".part")
        os.replace(dest + ".part", dest)
    return nome


def _vram_libera_mb(exe):
    try:
        out = subprocess.run([exe, "--list-devices"], capture_output=True, text=True, timeout=60,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (OSError, subprocess.TimeoutExpired):
        return 0
    liberi = [int(x) for x in re.findall(r"(\d+) MiB free", out)]
    return max(liberi) if liberi else 0


def _porta_libera():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def avvia(nome, log_dir, imp=None, attesa=180):
    """Avvia llama-server col modello; -> URL "compatibile OpenAI" da passare ad ai.Client."""
    global _processo
    ferma()
    motore, modello = cartella_motore(), presente(nome, imp)
    if not motore:
        raise FileNotFoundError("motore llama.cpp non trovato")
    if not modello:
        raise FileNotFoundError(f"modello {nome} non scaricato")
    exe = os.path.join(motore, "llama-server.exe")
    gpu = _vram_libera_mb(exe) >= MODELLI[nome]["mb"] * 1.3 + 600  # tutto il modello piu' il contesto
    porta = _porta_libera()
    os.makedirs(log_dir, exist_ok=True)
    log = open(os.path.join(log_dir, "ai_locale.log"), "w", encoding="utf-8")
    _processo = subprocess.Popen([exe, "-m", modello, "-c", "8192", "-ngl", "99" if gpu else "0",
                                  "--host", "127.0.0.1", "--port", str(porta)], stdout=log, stderr=log,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    url = f"http://127.0.0.1:{porta}"
    t0 = time.time()
    while time.time() - t0 < attesa:
        if _processo.poll() is not None:
            raise RuntimeError("il motore AI si è chiuso: vedi ai_locale.log")
        try:
            with urllib.request.urlopen(url + "/health", timeout=3) as r:
                if r.status == 200:
                    return {"url": url + "/v1", "gpu": gpu}
        except OSError:
            pass
        time.sleep(1)
    ferma()
    raise TimeoutError("il motore AI non risponde")


def ferma():
    global _processo
    if _processo is not None and _processo.poll() is None:
        _processo.terminate()
        try:
            _processo.wait(10)
        except subprocess.TimeoutExpired:
            _processo.kill()
    _processo = None
