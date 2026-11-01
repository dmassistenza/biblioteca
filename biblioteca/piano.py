"""Dal tavolo delle proposte al piano delle operazioni (nessun file viene toccato).
Nome uniforme: "Prefisso - Titolo, sottotitolo - Autore.ext"; nelle collezioni
"Categoria\\Collezione\\Prefisso - Collezione NN, Titolo - Autore.ext".
Nomi gia' usati -> "(otra copia)"; percorso al massimo 250 caratteri.
"""
import difflib
import os
from collections import Counter

from . import impostazioni
from .regole import MAX_PATH, nome_sicuro

SIMILE_COLLEZIONE = 0.85


def corpo_nome(p, prefisso):
    tit = p["titolo"].strip()
    coll = p["collezione"].strip()
    if coll and str(p.get("volume", "")).strip():
        corto = coll
        if corto.lower().startswith(prefisso.lower() + " "):  # "Comentario Bíblico Moody" -> "Bíblico Moody"
            corto = corto[len(prefisso) + 1:]
        tit = f"{corto} {p['volume']}, {tit}" if tit else f"{corto} {p['volume']}"
    if p.get("sottotitolo", "").strip():
        tit += ", " + p["sottotitolo"].strip()
    return tit


def estensione(p):
    ext = os.path.splitext(p["percorso"])[1].lower()
    return ext if ext in (".pdf", ".epub", ".mobi") else ".epub"  # EPUB senza estensione


def _fuori(base, p, tag):
    """Destinazione per duplicati e altri file: stessa struttura di cartelle della sorgente."""
    rel = os.path.join(os.path.basename(p["sorgente"].rstrip("\\/")) if p.get("sorgente") else "", p["cartella"], p["file"])
    d = os.path.join(base, rel)
    if len(d) > MAX_PATH:  # nome originale troppo lungo: si accorcia, l'hash lo tiene unico
        stem, ext = os.path.splitext(p["file"])
        coda = f"~{(p.get('sha256') or tag)[:8]}{ext}"
        testa = os.path.dirname(d)
        d = os.path.join(testa, stem[:max(10, MAX_PATH - len(testa) - 1 - len(coda))].rstrip(" .-") + coda)
    return d


def costruisci(imp, proposte, sorgenti_di=None):
    """-> {"operazioni": [...], "errori": [...], "avvisi": [...], "righe": [...]}.
    sorgenti_di: {n: cartella sorgente} per ricostruire la struttura in _duplicati e _altri_file."""
    cart = impostazioni.cartelle(imp)
    bib = cart["biblioteca"]
    errori, avvisi, ops, righe = [], [], [], []
    for p in proposte:
        p["sorgente"] = (sorgenti_di or {}).get(p["n"], p.get("sorgente", ""))
    imp_ = [p for p in proposte if p["decisione"] == "IMPORTA"]
    for p in imp_:
        if p["categoria"] not in imp["categorie"]:
            errori.append(f"n.{p['n']}: categoria mancante o sconosciuta ({p['categoria'] or 'vuota'})")
        if not p["titolo"].strip():
            errori.append(f"n.{p['n']}: titolo vuoto ({p['file']})")
    # collezioni con un solo libro non giustificano una sottocartella (se non esiste gia')
    per_coll = Counter((p["categoria"], p["collezione"]) for p in imp_ if p["collezione"])
    for p in imp_:
        k = (p["categoria"], p["collezione"])
        if p["collezione"] and per_coll[k] == 1 and not os.path.isdir(os.path.join(bib, p["categoria"], nome_sicuro(p["collezione"]))):
            avvisi.append(f"n.{p['n']}: collezione \"{p['collezione']}\" con un solo libro: il libro va nella categoria")
            p["nota"] = (p["nota"] + "; " if p["nota"] else "") + f"Serie {p['collezione']} (unico volume)"
            p["collezione"], p["volume"] = "", ""
    # collezioni con nomi quasi uguali (anche rispetto a quelle gia' in Biblioteca)
    nomi_coll = {(p["categoria"], p["collezione"]) for p in imp_ if p["collezione"]}
    esistenti = set()
    for c in {p["categoria"] for p in imp_}:
        d = os.path.join(bib, c)
        if os.path.isdir(d):
            esistenti |= {(c, x) for x in os.listdir(d) if os.path.isdir(os.path.join(d, x))}
    tutte = sorted(nomi_coll | esistenti)
    for i, (c1, a) in enumerate(tutte):
        for c2, b in tutte[i + 1:]:
            if c1 == c2 and (c1, a) in nomi_coll | {(c2, b)} and a != b and \
                    difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio() >= SIMILE_COLLEZIONE:
                avvisi.append(f"collezioni quasi uguali in {c1}: \"{a}\" e \"{b}\"")
    # destinazioni
    esist = set()
    if bib and os.path.isdir(bib):
        for dp, dirs, fns in os.walk(bib):
            dirs[:] = [d for d in dirs if not d.startswith("_")]
            esist |= {os.path.join(dp, f).lower() for f in fns}
    steli = {os.path.splitext(x)[0] for x in esist}
    usate = set()
    for p in sorted(proposte, key=lambda p: p["n"]):
        dest, tipo = "", ""
        if p["decisione"] == "IMPORTA" and p["categoria"] in imp["categorie"] and p["titolo"].strip():
            pref = impostazioni.prefisso(imp, p["categoria"])
            cartella = os.path.join(bib, p["categoria"], nome_sicuro(p["collezione"])) if p["collezione"] else os.path.join(bib, p["categoria"])
            corpo = corpo_nome(p, pref)
            ext = estensione(p)
            for tentativo in range(3):  # troppo lungo: prima si toglie il sottotitolo, poi si accorcia il titolo
                for k in range(1, 20):
                    t = corpo if k == 1 else f"{corpo} (otra copia{'' if k == 2 else ' ' + str(k - 1)})"
                    stem = os.path.join(cartella, nome_sicuro(f"{pref} - {t}" + (f" - {p['autore']}" if p["autore"].strip() else "")))
                    cand = stem + ext
                    if cand.lower() not in esist and cand.lower() not in usate and stem.lower() not in steli:
                        break
                if len(cand) <= MAX_PATH:
                    break
                if p.get("sottotitolo"):
                    avvisi.append(f"n.{p['n']}: nome troppo lungo, tolto il sottotitolo")
                    p = {**p, "sottotitolo": ""}
                    corpo = corpo_nome(p, pref)
                else:
                    resto = max(15, len(corpo) - (len(cand) - MAX_PATH) - 1)
                    corpo = corpo[:resto].rsplit(" ", 1)[0].rstrip(" ,.-")
                    avvisi.append(f"n.{p['n']}: nome troppo lungo, titolo accorciato")
            if k > 1:
                avvisi.append(f"n.{p['n']}: nome gia' usato, aggiunto \"(otra copia)\"")
            if len(cand) > MAX_PATH:
                errori.append(f"n.{p['n']}: percorso troppo lungo ({len(cand)} caratteri), accorciare il titolo")
            usate.add(cand.lower())
            dest, tipo = cand, "SPOSTA"
        elif p["decisione"] == "DUPLICATO":
            dest, tipo = _fuori(cart["duplicati"], p, "dup"), "DUPLICATO"
        elif p["decisione"] == "ALTRI_FILE":
            dest, tipo = _fuori(cart["altri_file"], p, "altro"), "SPOSTA"
        if dest and p["decisione"] != "IMPORTA":
            base, ext = os.path.splitext(dest)
            k = 1
            while dest.lower() in usate or os.path.exists(dest):  # mai sovrascrivere
                k += 1
                dest = f"{base}~{k}{ext}"
            usate.add(dest.lower())
        if dest:
            ops.append({"n": p["n"], "tipo": tipo, "da": p["percorso"], "a": dest, "sha256": p.get("sha256", "")})
        righe.append({"n": p["n"], "decisione": p["decisione"], "motivo": p["motivo"], "file_attuale": p["file"],
                      "nuovo_nome": os.path.basename(dest) if dest else "", "categoria": p["categoria"],
                      "collezione": p["collezione"], "titolo": p["titolo"], "autore": p["autore"],
                      "nota": p["nota"], "segnalazioni": ", ".join(p["flags"]),
                      "destinazione": dest or "(resta dov'è)"})
    return {"operazioni": ops, "errori": errori, "avvisi": avvisi, "righe": righe}
