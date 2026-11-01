"""Esecuzione del piano, annullamento e verifica. NON CANCELLA MAI: solo os.rename, mai sovrascrivere.
Controlli per ogni operazione (se uno fallisce, in esecuzione reale non si sposta NULLA):
- sorgente esistente e con lo stesso SHA-256 dell'inventario;
- sorgente dentro le cartelle sorgente ammesse;
- destinazione dentro Biblioteca, _duplicati o _altri_file;
- niente cartelle protette;
- destinazione libera e mai ripetuta nel piano;
- percorso al massimo 250 caratteri.
Ogni spostamento riuscito viene scritto subito nel log, che non si sovrascrive mai e serve per annullare.
"""
import csv
import datetime
import glob
import os

from . import impostazioni
from .lettura import sha256
from .regole import MAX_PATH, dentro, lungo

CAMPI_LOG = ["quando", "n", "tipo", "da", "a", "sha256", "esito"]


def controlla(imp, ops, avanzamento=None):
    cart = impostazioni.cartelle(imp)
    destinazioni = [cart["biblioteca"], cart["duplicati"], cart["altri_file"]]
    problemi, viste = [], set()
    for i, o in enumerate(ops, 1):
        da, a = o["da"], o["a"]
        err = []
        if dentro(da, cart["protette"]) or dentro(a, cart["protette"]):
            err.append("tocca una cartella protetta")
        if o["tipo"] == "RINOMINA":
            if not dentro(da, [cart["biblioteca"]]):
                err.append("RINOMINA ammessa solo dentro la Biblioteca")
        elif not dentro(da, cart["sorgenti"]):
            err.append("sorgente fuori dalle cartelle sorgente")
        if not dentro(a, destinazioni):
            err.append("destinazione fuori da Biblioteca, _duplicati e _altri_file")
        if not os.path.isfile(lungo(da)):
            err.append("sorgente non trovata")
        elif o.get("sha256") and sha256(lungo(da)) != o["sha256"]:
            err.append("file cambiato dopo l'inventario (hash diverso)")
        if os.path.exists(lungo(a)):
            err.append("destinazione già esistente")
        if os.path.normcase(a) in viste:
            err.append("destinazione ripetuta nel piano")
        viste.add(os.path.normcase(a))
        if len(a) > MAX_PATH:
            err.append(f"percorso troppo lungo ({len(a)} caratteri)")
        if err:
            problemi.append({"n": o["n"], "da": da, "a": a, "problemi": err})
        if avanzamento:
            avanzamento(i, len(ops), os.path.basename(da))
    return problemi


def _nuovo_log(cartella, nome):
    os.makedirs(cartella, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    p = os.path.join(cartella, f"{nome}_{stamp}.csv")
    k = 1
    while os.path.exists(p):  # due esecuzioni nello stesso secondo: mai sovrascrivere un log
        k += 1
        p = os.path.join(cartella, f"{nome}_{stamp}_{k}.csv")
    return p


def esegui(imp, ops, reale, avanzamento=None, stop=None):
    """Simulazione (reale=False) o esecuzione. -> {"log", "problemi", "spostati", "interrotto"}."""
    cart = impostazioni.cartelle(imp)
    problemi = controlla(imp, ops, avanzamento)
    log = _nuovo_log(os.path.join(cart["dati"], "log"), "log" if reale else "simulazione")
    cattivi = {(p["n"], p["da"]) for p in problemi}
    spostati, interrotto = 0, False
    with open(log, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPI_LOG, extrasaction="ignore")
        w.writeheader()
        if reale and problemi:
            for o in ops:
                w.writerow({**o, "quando": datetime.datetime.now().isoformat(timespec="seconds"),
                            "esito": "NON ESEGUITO (piano bloccato)"})
            return {"log": log, "problemi": problemi, "spostati": 0, "interrotto": False}
        for i, o in enumerate(ops, 1):
            if reale and stop is not None and stop.is_set():
                interrotto = True  # quello gia' fatto resta nel log e si puo' annullare
                break
            row = {"quando": datetime.datetime.now().isoformat(timespec="seconds"), **o}
            if (o["n"], o["da"]) in cattivi:
                row["esito"] = "PROBLEMA"
            elif not reale:
                row["esito"] = "OK (simulato)"
            else:
                os.makedirs(lungo(os.path.dirname(o["a"])), exist_ok=True)
                os.rename(lungo(o["da"]), lungo(o["a"]))
                row["esito"] = "SPOSTATO"
                spostati += 1
            w.writerow(row)
            f.flush()
            if avanzamento:
                avanzamento(i, len(ops), os.path.basename(o["a"]))
    return {"log": log, "problemi": problemi, "spostati": spostati, "interrotto": interrotto}


def leggi_log(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def elenco_log(imp):
    """Log delle esecuzioni reali (gli unici che si possono annullare), dal piu' recente."""
    cart = impostazioni.cartelle(imp)
    out = []
    for p in sorted(glob.glob(os.path.join(cart["dati"], "log", "log_*.csv")), reverse=True):
        if "_annull" in os.path.basename(p):
            continue
        righe = leggi_log(p)
        out.append({"log": p, "spostati": sum(r["esito"] == "SPOSTATO" for r in righe),
                    "annullato": bool(glob.glob(p[:-4] + "_annullato_*.csv"))})
    return out


def annulla(path_log, reale, avanzamento=None):
    """Rimette ogni file al posto di prima, in ordine inverso. Non sovrascrive: i conflitti si saltano.
    Le cartelle rimaste vuote restano (non si cancella nulla)."""
    righe = [r for r in leggi_log(path_log) if r["esito"] == "SPOSTATO"]
    tag = "annullato" if reale else "prova_annullamento"
    out = path_log[:-4] + f"_{tag}_{datetime.datetime.now():%Y%m%d_%H%M%S}.csv"
    ok = saltati = 0
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["da", "a", "esito"])
        w.writeheader()
        for i, r in enumerate(reversed(righe), 1):
            src, dst = r["a"], r["da"]
            if not os.path.isfile(lungo(src)):
                esito = "SALTATO: file non trovato nella nuova posizione"
            elif os.path.exists(lungo(dst)):
                esito = "SALTATO: posizione originale occupata"
            elif reale:
                os.makedirs(lungo(os.path.dirname(dst)), exist_ok=True)
                os.rename(lungo(src), lungo(dst))
                esito = "RIPRISTINATO"
            else:
                esito = "OK (simulato)"
            ok += esito.startswith(("RIPRISTINATO", "OK"))
            saltati += esito.startswith("SALTATO")
            w.writerow({"da": src, "a": dst, "esito": esito})
            if avanzamento:
                avanzamento(i, len(righe), os.path.basename(dst))
    return {"log": out, "ok": ok, "saltati": saltati}


def verifica(path_log, avanzamento=None):
    """Dopo l'esecuzione: ogni file e' nella destinazione con lo stesso hash e non e' piu' nella sorgente."""
    righe = [r for r in leggi_log(path_log) if r["esito"] == "SPOSTATO"]
    errori = []
    for i, r in enumerate(righe, 1):
        if not os.path.isfile(lungo(r["a"])):
            errori.append(f"manca: {r['a']}")
        elif r["sha256"] and sha256(lungo(r["a"])) != r["sha256"]:
            errori.append(f"hash diverso: {r['a']}")
        if os.path.exists(lungo(r["da"])):
            errori.append(f"ancora nella sorgente: {r['da']}")
        if avanzamento:
            avanzamento(i, len(righe), os.path.basename(r["a"]))
    return {"controllati": len(righe), "errori": errori}


def posizioni_attuali(imp):
    """sha256 -> posizione attuale, seguendo tutti i log reali (e gli annullamenti)."""
    cart = impostazioni.cartelle(imp)
    dove = {}
    for p in sorted(glob.glob(os.path.join(cart["dati"], "log", "log_*.csv"))):
        nome = os.path.basename(p)
        if "prova_annullamento" in nome:
            continue
        if "_annullato_" in nome:
            for r in leggi_log(p):
                if r["esito"] == "RIPRISTINATO":
                    for h, pos in list(dove.items()):
                        if pos == r["da"]:
                            dove[h] = r["a"]
            continue
        for r in leggi_log(p):
            if r["esito"] == "SPOSTATO" and r["tipo"] in ("SPOSTA", "RINOMINA"):
                dove[r["sha256"]] = r["a"]
    return dove
