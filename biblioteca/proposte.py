"""Proposte per ogni file delle sorgenti (nessun file viene toccato):
decisione, categoria (3 proposte con sicurezza), collezione, volume, titolo, sottotitolo, autore, note.
Le proposte si correggono nella tabella dell'interfaccia e poi diventano il piano (piano.py).
"""
import json
import os
import re

from . import duplicati, nomi
from .classifica import ClassificatoreLR, caratteristiche
from .regole import nome_sicuro
from .testo import split_name

DECISIONI = ("IMPORTA", "GIA_IN_BIBLIOTECA", "DUPLICATO", "DOPPIONE_PROBABILE", "NON_IMPORTARE", "ALTRI_FILE")
MIN_ADDESTRAMENTO = 150      # libri in Biblioteca per addestrare il classificatore sulla Biblioteca dell'utente
MODELLO_BASE = os.path.join(os.path.dirname(__file__), "risorse", "modello_categorie.pkl")


def _anteprima(c):
    return (c or {}).get("anteprima", "")


def addestra(imp, cache_bib):
    """Classificatori di categoria e collezione e stile dei nomi, imparati dalla Biblioteca.
    Con una Biblioteca piccola o vuota si usa il modello di base (solo categorie)."""
    cats = set(imp["categorie"])
    esempi, esempi_coll, titoli, autori = [], [], [], []
    for rel, v in cache_bib.items():
        c, k, t, a = split_name(rel)
        if c not in cats:
            continue
        f = caratteristiche(rel, v.get("meta") or {}, _anteprima(v))
        esempi.append((f, c))
        esempi_coll.append((f, c + "|" + k))
        titoli.append(t)
        autori.append(a)
    out = {"stile": nomi.Stile(titoli, autori), "categorie": None, "collezioni": None, "origine": ""}
    if len(esempi) >= MIN_ADDESTRAMENTO and len({c for _, c in esempi}) >= 3:
        out["categorie"] = ClassificatoreLR().addestra(esempi)
        if any(k.split("|", 1)[1] for _, k in esempi_coll):
            out["collezioni"] = ClassificatoreLR().addestra(esempi_coll)
        out["origine"] = "biblioteca"
    elif os.path.exists(MODELLO_BASE):
        m = ClassificatoreLR.carica(MODELLO_BASE)
        if set(m.model.classes_) <= cats:  # solo se le categorie sono le stesse del modello di base
            out["categorie"], out["origine"] = m, "base"
    return out


def _flag(p, testo):
    p["flags"].append(testo)


def calcola(imp, schede, cache, cache_bib, modelli=None, avanzamento=None):
    modelli = modelli or addestra(imp, cache_bib)
    idx = duplicati.indice_biblioteca(cache_bib)
    gruppi = duplicati.identici(schede)
    tenuto = {h: g[0]["n"] for h, g in gruppi.items()}
    soglia = imp.get("soglia_sicura", 0.7)
    per_n = {s["n"]: s for s in schede}
    libri = [s for s in schede if s["tipo"] == "libro"]
    feats = {s["n"]: caratteristiche(s["percorso"], s.get("meta") or {}, _anteprima(cache.get(s["percorso"])))
             for s in libri}
    cat_top, coll_top = {}, {}
    if libri and modelli["categorie"]:
        for s, top in zip(libri, modelli["categorie"].proponi_molti([feats[s["n"]] for s in libri], 3)):
            cat_top[s["n"]] = top
    if libri and modelli["collezioni"]:
        for s, top in zip(libri, modelli["collezioni"].proponi_molti([feats[s["n"]] for s in libri], 1)):
            coll_top[s["n"]] = top[0]
    proposte = []
    for i, s in enumerate(schede, 1):
        p = {"n": s["n"], "percorso": s["percorso"], "file": s["file"], "cartella": s["cartella"], "sha256": s.get("sha256", ""),
             "formato": s.get("formato") or s["estensione"].lstrip("."), "pagine": s.get("pagine") or 0,
             "isbn": s.get("isbn") or [], "testo": s.get("testo", ""), "decisione": "IMPORTA", "motivo": "",
             "categoria": "", "cat_proposte": [], "sicurezza": 0.0, "collezione": "", "volume": "",
             "titolo": "", "sottotitolo": "", "autore": "", "fonte": "", "nota": "", "flags": [], "simili": []}
        t = s["tipo"]
        if t == "non_libro":
            p.update(decisione="ALTRI_FILE", motivo="non è un libro")
        elif t == "vuoto":
            p.update(decisione="NON_IMPORTARE", motivo="file vuoto (0 byte)")
        elif t == "non_leggibile":
            p.update(decisione="NON_IMPORTARE", motivo="azw3: serve Calibre per convertirlo in EPUB")
        elif t == "da_leggere":
            p.update(decisione="NON_IMPORTARE", motivo="inventario interrotto prima di questo file")
        elif s.get("stato") in ("errore", "protetto"):
            p.update(decisione="NON_IMPORTARE", motivo="protetto da password" if s["stato"] == "protetto" else
                     "file danneggiato: " + (s.get("errore") or "")[:80])
            _flag(p, "da controllare")
        if t != "libro" or p["decisione"] != "IMPORTA":
            proposte.append(p)
            continue
        # duplicati
        h = s.get("sha256")
        if h in tenuto and tenuto[h] != s["n"]:
            p.update(decisione="DUPLICATO", motivo=f"copia identica del n.{tenuto[h]}")
        else:
            dec, motivo, simili = duplicati.in_biblioteca(s, idx)
            p["simili"] = simili
            if dec:
                p.update(decisione="GIA_IN_BIBLIOTECA", motivo=motivo)
                if dec == "isbn":
                    _flag(p, "probabile doppione")
            elif simili:
                _flag(p, "titolo simile in Biblioteca")
        # categoria
        top = cat_top.get(s["n"], [])
        p["cat_proposte"] = [[c, round(x, 3)] for c, x in top]
        if top:
            p["categoria"], p["sicurezza"] = top[0][0], round(top[0][1], 3)
        if not top or top[0][1] < soglia:
            _flag(p, "categoria incerta")
        ct = coll_top.get(s["n"])
        if ct and ct[0].split("|", 1)[0] == p["categoria"]:
            p["collezione"] = ct[0].split("|", 1)[1]
        # nomi
        c = cache.get(s["percorso"], {})
        nm = nomi.proponi(s["percorso"], s.get("meta") or {}, modelli["stile"], c.get("prime_pagine") or [])
        tit = nm["titolo"]
        if ", " in tit:
            tit, sub = tit.split(", ", 1)
            p["sottotitolo"] = sub
        p.update(titolo=tit, autore=nm["autore"], volume=nm["volume"] or "", fonte=nm["fonte"])
        if not p["autore"]:
            _flag(p, "autore mancante")
        if s.get("testo") in ("scansione", "poco") or s.get("stato") == "solo_immagini":
            _flag(p, "senza testo")
        if p["categoria"] == "No Cristiano":
            _flag(p, "da controllare")
        proposte.append(p)
        if avanzamento:
            avanzamento(i, len(schede), s["file"])
    # probabili doppioni tra le sorgenti: resta fermo quello con meno testo
    per_n_p = {p["n"]: p for p in proposte}
    for a, b, motivo in duplicati.probabili_tra_sorgenti(schede):
        pa, pb = per_n_p[a], per_n_p[b]
        if pa["decisione"] != "IMPORTA" or pb["decisione"] != "IMPORTA":
            continue
        keep, other = sorted((pa, pb), key=lambda p: duplicati.da_tenere(per_n[p["n"]]), reverse=True)
        other.update(decisione="DOPPIONE_PROBABILE", motivo=f"{motivo}: sembra il n.{keep['n']}")
        _flag(other, "probabile doppione")
    return proposte


def da_fare_ai(proposte, solo=None):
    """Libri da importare che l'AI non ha ancora visto e che l'utente non ha corretto a mano."""
    return [p for p in proposte if p["decisione"] == "IMPORTA" and p["fonte"] not in ("manuale", "ai")
            and (solo is None or p["n"] in solo)]


def applica_ai(proposte, client, stile, cache, avanzamento=None, stop=None, solo=None, pausa=0.0, salva_ogni=None):
    """Titolo, sottotitolo e autore dall'AI per i libri da importare (o solo per i numeri in `solo`).
    I campi gia' corretti a mano (fonte "manuale") non si toccano. Se si interrompe (o finisce il limite
    gratuito del giorno) si riprende da dove si era arrivati: quelli fatti hanno fonte "ai"."""
    import time
    from . import ai
    da_fare = da_fare_ai(proposte, solo)
    for i, p in enumerate(da_fare, 1):
        if stop is not None and stop.is_set():
            break
        if salva_ogni and i % 10 == 0:
            salva_ogni()
        if pausa and i > 1:
            time.sleep(pausa)
        c = cache.get(p["percorso"], {})
        if not c.get("prime_pagine") and not c.get("meta"):
            continue
        try:
            r, _ = client.proponi(p["percorso"], c.get("meta") or {}, c.get("prime_pagine") or [])
        except ai.ErroreAI as e:
            if e.tipo in ("chiave", "limite"):
                raise
            p["nota"] = (p["nota"] + "; " if p["nota"] else "") + "AI: nessuna risposta"
            continue
        r = ai.rifinisci(r, stile)
        if r["titolo"]:
            p.update(titolo=r["titolo"], sottotitolo=r["sottotitolo"], fonte="ai")
            if r["autore"]:
                p["autore"] = r["autore"]
                if "autore mancante" in p["flags"]:
                    p["flags"].remove("autore mancante")
        if avanzamento:
            avanzamento(i, len(da_fare), p["file"])
    return proposte


def numera_collezione(proposte, categoria, collezione, biblioteca=""):
    """Numeri di volume 01, 02... ai libri di una collezione, dopo quelli gia' presenti in Biblioteca,
    nell'ordine dei numeri gia' trovati e poi del titolo."""
    gia = 0
    cart = os.path.join(biblioteca, categoria, nome_sicuro(collezione)) if biblioteca else ""
    if cart and os.path.isdir(cart):
        for fn in os.listdir(cart):
            m = re.search(r" (\d{1,3})(?:,| - )", fn)
            if m:
                gia = max(gia, int(m.group(1)))
    libri = [p for p in proposte if p["decisione"] == "IMPORTA" and p["categoria"] == categoria and p["collezione"] == collezione]
    libri.sort(key=lambda p: (int(p["volume"]) if str(p["volume"]).isdigit() else 10**6, p["titolo"].casefold()))
    larghezza = 3 if gia + len(libri) >= 100 else 2
    for k, p in enumerate(libri, gia + 1):
        p["volume"] = str(k).zfill(larghezza)
    return len(libri)


def salva(path, proposte):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(proposte, f, ensure_ascii=False, indent=0)
    os.replace(tmp, path)


def carica(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)
