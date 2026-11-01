"""Analisi di molti libri in parallelo, con cache incrementale: si rileggono solo i file nuovi o cambiati.
La usano sia l'inventario delle sorgenti sia il catalogo della Biblioteca.
Si puo' interrompere (stop) e riprendere: la cache viene salvata spesso.
"""
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

from .lettura import analizza_file, sha256
from .regole import lungo

SALVA_OGNI = 40


def firma(path):
    st = os.stat(lungo(path))
    return f"{st.st_size}:{int(st.st_mtime)}"


def _uno(path):
    try:
        r = analizza_file(lungo(path))
    except Exception as e:  # noqa: BLE001  un libro rotto non deve fermare tutto
        r = {"formato": "", "pagine": 0, "stato": "errore", "errore": str(e)[:200], "meta": {}}
    try:
        r["sha256"] = sha256(lungo(path))
    except OSError as e:
        r.update(stato="errore", errore=f"lettura: {e}"[:200], sha256="")
    r["byte"] = os.path.getsize(lungo(path))
    return r


def carica_cache(path):
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def salva_cache(path, cache):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    os.replace(tmp, path)


def analizza_molti(voci, cache_path, avanzamento=None, stop=None, processi=None):
    """voci: lista di (chiave, percorso). Restituisce la cache {chiave: risultato} aggiornata.
    avanzamento(fatti, totale, nome); stop: threading.Event per interrompere."""
    cache = carica_cache(cache_path)
    voci = list(voci)
    firme = {}
    for k, p in voci:
        try:
            firme[k] = firma(p)
        except OSError:
            firme[k] = ""
    da_fare = [(k, p) for k, p in voci if cache.get(k, {}).get("firma") != firme[k] or not cache[k].get("sha256")]
    tot = len(da_fare)
    if avanzamento:
        avanzamento(0, tot, "")
    if da_fare:
        n_proc = processi or max(1, (os.cpu_count() or 2) - 1)
        fatti, ultimo = 0, time.time()
        with ProcessPoolExecutor(max_workers=n_proc) as ex:
            futs = {ex.submit(_uno, p): (k, p) for k, p in da_fare}
            try:
                for fu in as_completed(futs):
                    k, p = futs[fu]
                    cache[k] = {"firma": firme[k], **fu.result()}
                    fatti += 1
                    if avanzamento:
                        avanzamento(fatti, tot, os.path.basename(p))
                    if fatti % SALVA_OGNI == 0 or time.time() - ultimo > 30:
                        salva_cache(cache_path, cache)
                        ultimo = time.time()
                    if stop is not None and stop.is_set():
                        for f in futs:
                            f.cancel()
                        break
            finally:
                salva_cache(cache_path, cache)
    return cache
