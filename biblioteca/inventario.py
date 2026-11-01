"""Inventario in SOLA LETTURA delle cartelle sorgente e della Biblioteca.
Per ogni file: SHA-256, dimensione, formato, pagine, testo delle prime pagine, ISBN, edizione,
prologo, lingua stimata, errori e file protetti. Si puo' interrompere e riprendere (cache).
"""
import os
import re

from . import analisi, impostazioni
from .lettura import formato
from .regole import EBOOK, NON_LIBRI, dentro, percorri

STOP = {
    "es": set("el la los las de del que y en por para con una un es se su al como más".split()),
    "en": set("the and of to in that is for with as by this be are his he not".split()),
    "it": set("il lo gli di che e in per con una un è si del della nel come non sono".split()),
    "pt": set("o os as de do da que e em para com uma um não".split()),
}


def lingua(testo):
    words = re.findall(r"[a-záéíóúñèàòùçãõ]+", (testo or "").lower())
    if len(words) < 30:
        return ""
    punti = {k: sum(1 for w in words if w in v) for k, v in STOP.items()}
    best = max(punti, key=punti.get)
    return best if punti[best] >= 5 else ""


def tipo_file(path):
    """libro | non_libro | vuoto | non_leggibile (azw3: servirebbe Calibre)."""
    fn = os.path.basename(path).lower()
    if fn in NON_LIBRI:
        return "non_libro"
    try:
        if os.path.getsize(path) == 0:
            return "vuoto"
    except OSError:
        return "non_libro"
    ext = os.path.splitext(fn)[1]
    if ext in (".azw3", ".azw"):
        return "non_leggibile"
    if ext in EBOOK or formato(path) == "epub":  # anche gli EPUB senza estensione
        return "libro"
    return "non_libro"


def escluse(cart):
    """Cartelle che l'inventario delle sorgenti non deve mai aprire."""
    return [c for c in cart["protette"] + [cart["biblioteca"], cart["duplicati"], cart["altri_file"], cart["dati"]] if c]


def file_sorgenti(cart):
    out = []
    for src in cart["sorgenti"]:
        if not os.path.isdir(src) or dentro(src, cart["protette"]):
            continue
        for p in percorri(src, escluse(cart)):
            out.append((src, p))
    return out


def file_biblioteca(cart):
    """Libri della Biblioteca: chiave = percorso relativo. Le cartelle con "_" (dati, duplicati) si saltano."""
    bib = cart["biblioteca"]
    if not bib or not os.path.isdir(bib):
        return []
    out = []
    for dp, dirs, fns in os.walk(bib):
        dirs[:] = sorted(d for d in dirs if not d.startswith("_") and not dentro(os.path.join(dp, d), cart["protette"]))
        for fn in sorted(fns):
            p = os.path.join(dp, fn)
            if tipo_file(p) == "libro":
                out.append((os.path.relpath(p, bib), p))
    return out


def analizza_biblioteca(imp, avanzamento=None, stop=None):
    cart = impostazioni.cartelle(imp)
    voci = file_biblioteca(cart)
    cache = analisi.analizza_molti(voci, os.path.join(cart["dati"], "catalogo_cache.json"), avanzamento, stop)
    chiavi = {k for k, _ in voci}
    if stop is None or not stop.is_set():  # libri tolti o rinominati escono dalla cache
        cache = {k: v for k, v in cache.items() if k in chiavi}
        analisi.salva_cache(os.path.join(cart["dati"], "catalogo_cache.json"), cache)
    return cache


def semina_catalogo(imp, cache_inv):
    """Dopo un'esecuzione: i libri appena entrati in Biblioteca hanno gia' l'analisi dell'inventario.
    La si copia nella cache del catalogo (con la firma nuova), cosi' non si rileggono."""
    from .esecuzione import elenco_log, leggi_log
    cart = impostazioni.cartelle(imp)
    path = os.path.join(cart["dati"], "catalogo_cache.json")
    cache = analisi.carica_cache(path)
    n = 0
    for lg in elenco_log(imp):
        for r in leggi_log(lg["log"]):
            if r["esito"] != "SPOSTATO" or not dentro(r["a"], [cart["biblioteca"]]) or not os.path.isfile(r["a"]):
                continue
            rel = os.path.relpath(r["a"], cart["biblioteca"])
            if rel not in cache and r["da"] in cache_inv:
                cache[rel] = {**cache_inv[r["da"]], "firma": analisi.firma(r["a"])}
                n += 1
    if n:
        analisi.salva_cache(path, cache)
    return n


def esegui(imp, avanzamento=None, stop=None):
    """Inventario delle sorgenti -> (schede, cache). Una scheda per file, in ordine di cartella;
    la cache ha anche il testo delle prime pagine, che serve alle proposte e all'anteprima."""
    cart = impostazioni.cartelle(imp)
    tutti = file_sorgenti(cart)
    libri = [(p, p) for _, p in tutti if tipo_file(p) == "libro"]
    cache = analisi.analizza_molti(libri, os.path.join(cart["dati"], "inventario_cache.json"), avanzamento, stop)
    schede = []
    for n, (src, p) in enumerate(tutti, 1):
        t = tipo_file(p)
        rel = os.path.relpath(p, src)
        s = {"n": n, "percorso": p, "sorgente": src, "cartella": os.path.dirname(rel), "file": os.path.basename(p),
             "estensione": os.path.splitext(p)[1].lower(), "tipo": t}
        try:
            s["byte"] = os.path.getsize(p)
        except OSError:
            s["byte"] = 0
        if t == "libro":
            c = cache.get(p)
            if c is None:  # interrotto prima di arrivare a questo file
                s["tipo"] = "da_leggere"
            else:
                s.update({k: c.get(k) for k in ("sha256", "formato", "pagine", "stato", "errore", "meta", "isbn",
                                                 "edizione", "testo_edizione", "testo", "tipo_prologo", "prologo")})
                s["lingua"] = lingua(c.get("anteprima", ""))
        schede.append(s)
    return schede, cache
