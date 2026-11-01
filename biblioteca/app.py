"""Finestra del programma (pywebview, licenza BSD): l'interfaccia e' una pagina HTML in risorse/app.html,
nello stile del catalogo, in IT, EN ed ES. Questa classe Api e' quello che la pagina puo' chiamare.
I lavori lunghi girano in un thread: la pagina chiede ogni mezzo secondo a che punto sono.
Tutto quello che serve per riprendere (inventario, proposte, piano) si salva nella cartella dei dati.
"""
import base64
import ctypes
import json
import os
import threading
import traceback

from . import (__version__, ai, ai_locale, analisi, catalogo, chiavi, esecuzione, excel, impostazioni,
               inventario, lettura, piano, proposte)

RISORSE = os.path.join(os.path.dirname(__file__), "risorse")
CAMPI_MODIFICABILI = {"decisione", "motivo", "categoria", "collezione", "volume", "titolo", "sottotitolo", "autore", "nota"}


def lingua_windows():
    try:
        lid = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
        return {0x10: "it", 0x0A: "es"}.get(lid, "en")
    except (AttributeError, OSError):
        return "en"


class Lavoro:
    def __init__(self, nome, funzione):
        self.nome, self.stop = nome, threading.Event()
        self.stato = {"nome": nome, "fatti": 0, "totale": 0, "cosa": "", "fase": "", "finito": False,
                      "errore": "", "risultato": None}
        self.t = threading.Thread(target=self._gira, args=(funzione,), daemon=True)
        self.t.start()

    def avanzamento(self, fase=""):
        def f(fatti, totale, cosa):
            self.stato.update(fatti=fatti, totale=totale, cosa=cosa, fase=fase)
        return f

    def _gira(self, funzione):
        try:
            self.stato["risultato"] = funzione(self)
        except ai.ErroreAI as e:
            self.stato["errore"] = f"AI-{e.tipo}: {e}"
        except Exception as e:  # noqa: BLE001  l'errore va mostrato nella finestra, non perso
            self.stato["errore"] = f"{type(e).__name__}: {e}"
            traceback.print_exc()
        finally:
            self.stato["finito"] = True


class Api:
    def __init__(self):
        self._imp = impostazioni.carica()
        if not self._imp["lingua"]:
            self._imp["lingua"] = lingua_windows()
        self._finestra = None
        self._lavoro = None
        self._schede = self._cinv = self._cbib = self._prop = self._piano = self._modelli = None
        self._carica_stato()

    # ------------------------------------------------------------------ stato salvato
    def _dati(self, nome=""):
        d = impostazioni.cartelle(self._imp)["dati"]
        return os.path.join(d, nome) if nome else d

    def _carica_stato(self):
        self._schede = self._prop = self._piano = None
        try:
            if os.path.exists(self._dati("inventario.json")):
                with open(self._dati("inventario.json"), encoding="utf-8") as f:
                    self._schede = json.load(f)
            if os.path.exists(self._dati("proposte.json")):
                self._prop = proposte.carica(self._dati("proposte.json"))
        except (OSError, json.JSONDecodeError):
            pass

    def _salva_proposte(self):
        if self._prop is not None:
            os.makedirs(self._dati(), exist_ok=True)
            proposte.salva(self._dati("proposte.json"), self._prop)

    def _cache_inv(self):
        if self._cinv is None:
            self._cinv = analisi.carica_cache(self._dati("inventario_cache.json"))
        return self._cinv

    def _cache_bib(self):
        if self._cbib is None:
            self._cbib = analisi.carica_cache(self._dati("catalogo_cache.json"))
        return self._cbib

    # ------------------------------------------------------------------ generale
    def info(self):
        cart = impostazioni.cartelle(self._imp)
        logs = esecuzione.elenco_log(self._imp) if cart["biblioteca"] else []
        return {"versione": __version__, "imp": self._imp, "cartelle": cart,
                "inventario": len(self._schede or []), "proposte": len(self._prop or []),
                "piano": bool(self._piano), "log": logs[:20], "lavoro": self.stato_lavoro(),
                "esiste_catalogo": os.path.isfile(os.path.join(cart["biblioteca"], "Catalogo.html")) if cart["biblioteca"] else False}

    def salva_impostazioni(self, nuove):
        cambia_bib = nuove.get("biblioteca", self._imp["biblioteca"]) != self._imp["biblioteca"]
        for k, v in nuove.items():
            if k in impostazioni.PREDEFINITE:
                if k == "ai":
                    self._imp["ai"].update(v)
                else:
                    self._imp[k] = v
        impostazioni.salva(self._imp)
        if cambia_bib:
            self._cinv = self._cbib = self._modelli = None
            self._carica_stato()
        return self.info()

    def scegli_cartella(self):
        import webview
        r = self._finestra.create_file_dialog(webview.FileDialog.FOLDER)
        return r[0] if r else ""

    def scegli_file(self, filtro="Modello AI (*.gguf)"):
        import webview
        r = self._finestra.create_file_dialog(webview.FileDialog.OPEN, file_types=(filtro,))
        return r[0] if r else ""

    def apri(self, percorso):
        """Apre un file o una cartella con il programma di Windows (Excel, il browser, Esplora risorse)."""
        if percorso and os.path.exists(percorso):
            os.startfile(percorso)  # noqa: S606
            return True
        return False

    def apri_manuale(self, lingua="it"):
        import pathlib
        import webbrowser
        webbrowser.open(pathlib.Path(RISORSE, "manuale.html").as_uri() + "#lang=" + lingua)

    def apri_link(self, url):
        import webbrowser
        if url.startswith("https://"):
            webbrowser.open(url)

    # ------------------------------------------------------------------ lavori lunghi
    def stato_lavoro(self):
        return dict(self._lavoro.stato) if self._lavoro else None

    def ferma(self):
        if self._lavoro:
            self._lavoro.stop.set()

    def _avvia(self, nome, funzione):
        if self._lavoro and not self._lavoro.stato["finito"]:
            return {"errore": "occupato"}
        self._lavoro = Lavoro(nome, funzione)
        return {"ok": True}

    def _controlla_cartelle(self):
        cart = impostazioni.cartelle(self._imp)
        if not cart["biblioteca"]:
            raise ValueError("cartelle: manca la Biblioteca")
        if not cart["sorgenti"]:
            raise ValueError("cartelle: manca una cartella da ordinare")
        for s in cart["sorgenti"]:
            if inventario.dentro(s, [cart["biblioteca"]]) or inventario.dentro(cart["biblioteca"], [s]):
                raise ValueError("cartelle: la Biblioteca e le cartelle da ordinare non devono stare una dentro l'altra")
        return cart

    def avvia_inventario(self):
        def f(lv):
            cart = self._controlla_cartelle()
            os.makedirs(cart["dati"], exist_ok=True)
            self._cbib = inventario.analizza_biblioteca(self._imp, lv.avanzamento("biblioteca"), lv.stop)
            if lv.stop.is_set():
                return {"interrotto": True}
            schede, self._cinv = inventario.esegui(self._imp, lv.avanzamento("inventario"), lv.stop)
            if lv.stop.is_set():
                return {"interrotto": True}
            lv.stato.update(fase="proposte", fatti=0, totale=0)
            self._modelli = proposte.addestra(self._imp, self._cbib)
            self._schede = schede
            with open(self._dati("inventario.json"), "w", encoding="utf-8") as fh:
                json.dump(schede, fh, ensure_ascii=False)
            self._prop = proposte.calcola(self._imp, schede, self._cinv, self._cbib, self._modelli, lv.avanzamento("proposte"))
            self._salva_proposte()
            self._piano = None
            xl = excel.inventario(schede, self._dati("Inventario.xlsx"))
            return {"file": len(schede), "libri": sum(s["tipo"] == "libro" for s in schede), "excel": xl,
                    "modello": self._modelli["origine"]}
        return self._avvia("inventario", f)

    # ------------------------------------------------------------------ duplicati e proposte
    def riepilogo(self):
        if not self._prop:
            return None
        from collections import Counter
        dec = Counter(p["decisione"] for p in self._prop)
        flg = Counter(f for p in self._prop for f in p["flags"])
        sicure = sum(1 for p in self._prop if p["decisione"] == "IMPORTA" and p["sicurezza"] >= self._imp["soglia_sicura"])
        doppioni = [self._riga(p) for p in self._prop if p["decisione"] in ("GIA_IN_BIBLIOTECA", "DOPPIONE_PROBABILE", "DUPLICATO")
                    or "titolo simile in Biblioteca" in p["flags"]]
        return {"decisioni": dict(dec), "segnalazioni": dict(flg), "sicure": sicure, "doppioni": doppioni[:500],
                "categorie": sorted(self._imp["categorie"]), "modello": (self._modelli or {}).get("origine", "")}

    def _riga(self, p):
        return {k: p.get(k) for k in ("n", "file", "cartella", "decisione", "motivo", "categoria", "cat_proposte", "sicurezza",
                                      "collezione", "volume", "titolo", "sottotitolo", "autore", "nota", "flags", "fonte",
                                      "formato", "pagine", "simili", "isbn")}

    def elenco(self, filtro="tutti", cerca="", pagina=0, per_pagina=100):
        if not self._prop:
            return {"righe": [], "totale": 0}
        soglia = self._imp["soglia_sicura"]
        flt = {
            "tutti": lambda p: True,
            "controllare": lambda p: p["decisione"] == "IMPORTA" and (p["flags"] or p["sicurezza"] < soglia),
            "importa": lambda p: p["decisione"] == "IMPORTA",
            "doppioni": lambda p: p["decisione"] in ("GIA_IN_BIBLIOTECA", "DUPLICATO", "DOPPIONE_PROBABILE")
                                  or "probabile doppione" in p["flags"] or "titolo simile in Biblioteca" in p["flags"],
            "esclusi": lambda p: p["decisione"] in ("NON_IMPORTARE", "ALTRI_FILE"),
        }.get(filtro, lambda p: p["categoria"] == filtro[4:] if filtro.startswith("cat:") else True)
        c = duplicati_chiave(cerca)
        sel = [p for p in self._prop if flt(p) and (not c or c in duplicati_chiave(
            " ".join([p["file"], p["titolo"], p["sottotitolo"], p["autore"], p["collezione"]])))]
        # in cima i casi incerti
        if filtro in ("controllare", "importa"):
            sel.sort(key=lambda p: (p["sicurezza"], p["n"]))
        return {"righe": [self._riga(p) for p in sel[pagina * per_pagina:(pagina + 1) * per_pagina]], "totale": len(sel)}

    def dettaglio(self, n):
        p = next((x for x in self._prop or [] if x["n"] == n), None)
        if not p:
            return None
        c = self._cache_inv().get(p["percorso"], {})
        dove = p["percorso"]
        if not os.path.isfile(dove) and p.get("sha256"):  # gia' spostato da un'esecuzione: lo si ritrova dai log
            dove = esecuzione.posizioni_attuali(self._imp).get(p["sha256"], dove)
        img = lettura.copertina(dove) if os.path.isfile(dove) else b""
        return {**self._riga(p), "percorso": dove, "pagine_testo": (c.get("prime_pagine") or [])[:4],
                "prologo": c.get("prologo", ""), "edizione": c.get("edizione", ""),
                "copertina": "data:image/png;base64," + base64.b64encode(img).decode() if img else ""}

    def aggiorna(self, n, campo, valore):
        if campo not in CAMPI_MODIFICABILI:
            return False
        for p in self._prop or []:
            if p["n"] == n:
                p[campo] = valore
                if campo in ("titolo", "sottotitolo", "autore"):
                    p["fonte"] = "manuale"  # l'AI non lo cambia piu'
                if campo == "categoria":
                    p["sicurezza"] = 1.0  # scelta dall'utente
                    p["flags"] = [f for f in p["flags"] if f != "categoria incerta"]
                if campo == "autore" and valore.strip():
                    p["flags"] = [f for f in p["flags"] if f != "autore mancante"]
                self._piano = None
                self._salva_proposte()
                return self._riga(p)
        return False

    def aggiorna_molti(self, numeri, campo, valore):
        for n in numeri:
            self.aggiorna(n, campo, valore)
        return len(numeri)

    def numera(self, categoria, collezione):
        k = proposte.numera_collezione(self._prop or [], categoria, collezione, impostazioni.cartelle(self._imp)["biblioteca"])
        self._piano = None
        self._salva_proposte()
        return k

    def collezioni(self, categoria):
        bib = impostazioni.cartelle(self._imp)["biblioteca"]
        d = os.path.join(bib, categoria)
        gia = sorted(x for x in os.listdir(d) if os.path.isdir(os.path.join(d, x))) if bib and os.path.isdir(d) else []
        nuove = sorted({p["collezione"] for p in self._prop or [] if p["categoria"] == categoria and p["collezione"]} - set(gia))
        return gia + nuove

    # ------------------------------------------------------------------ AI
    def ai_stato(self):
        a = self._imp["ai"]
        return {"servizio": a["servizio"], "modello": a["modello"], "modello_locale": a["modello_locale"],
                "chiavi": {s: chiavi.mascherata(chiavi.leggi(s)) for s in ("gemini", "groq", "mistral", "claude") if chiavi.leggi(s)},
                "locale": ai_locale.stato(self._imp), "modelli_claude": list(ai.MODELLI_CLAUDE),
                "da_fare": len(proposte.da_fare_ai(self._prop or []))}

    def ai_scegli(self, servizio, modello="", modello_locale=""):
        self._imp["ai"].update(servizio=servizio, modello=modello, **({"modello_locale": modello_locale} if modello_locale else {}))
        impostazioni.salva(self._imp)
        return self.ai_stato()

    def ai_salva_chiave(self, servizio, testo):
        k = ai.estrai_chiave(testo)
        if not k:
            return {"ok": False}
        chiavi.salva(servizio, k)
        return {"ok": True, "mascherata": chiavi.mascherata(k)}

    def ai_togli_chiave(self, servizio):
        chiavi.togli(servizio)
        return self.ai_stato()

    def _client(self, servizio, modello=""):
        if servizio == "locale":
            nome = self._imp["ai"]["modello_locale"]
            nome = ai_locale.consigliato() if nome == "auto" else nome
            if not ai_locale.presente(nome, self._imp):
                altro = "2B" if nome == "4B" else "4B"
                if not ai_locale.presente(altro, self._imp):
                    raise ai.ErroreAI("modello", "modello AI non scaricato")
                nome = altro
            r = ai_locale.avvia(nome, self._dati(), self._imp)
            cl = ai.crea_client("locale")
            cl.url = r["url"]
            return cl
        chiave = chiavi.leggi(servizio)
        if not chiave:
            raise ai.ErroreAI("chiave", "nessuna chiave salvata")
        return ai.crea_client(servizio, chiave, modello)

    def ai_prova(self, servizio, modello=""):
        try:
            cl = self._client(servizio, modello)
            return dict(zip(("ok", "messaggio"), ai.prova(cl)))
        except (ai.ErroreAI, OSError, RuntimeError, TimeoutError) as e:
            return {"ok": False, "messaggio": str(e)}
        finally:
            if servizio == "locale":
                ai_locale.ferma()

    def ai_stima(self, servizio, modello=""):
        da_fare = proposte.da_fare_ai(self._prop or [])
        n = len(da_fare)
        sec = {"locale": 11 if (self._imp["ai"]["modello_locale"] in ("auto", "4B") and ai_locale.consigliato() == "4B") else 5,
               "gemini": 7.5, "groq": 3.5, "mistral": 3, "claude": 3}.get(servizio, 5)
        out = {"libri": n, "minuti": round(n * sec / 60)}
        if servizio == "claude":
            cache = self._cache_inv()
            testi = [ai.messaggio_libro(p["percorso"], cache.get(p["percorso"], {}).get("meta") or {},
                                        cache.get(p["percorso"], {}).get("prime_pagine") or []) for p in da_fare]
            out["dollari"] = ai.stima_costo(testi, modello or "claude-opus-5-5")
        return out

    def ai_avvia(self, servizio, modello=""):
        def f(lv):
            lv.stato.update(fase="avvio AI")
            cl = self._client(servizio, modello)
            try:
                stile = (self._modelli or proposte.addestra(self._imp, self._cache_bib()))["stile"]
                pausa = ai.SERVIZI.get(servizio, {}).get("pausa", 0)
                prima = len(proposte.da_fare_ai(self._prop))
                proposte.applica_ai(self._prop, cl, stile, self._cache_inv(), lv.avanzamento("AI"), lv.stop,
                                    pausa=pausa, salva_ogni=self._salva_proposte)
            finally:
                self._salva_proposte()
                if servizio == "locale":
                    ai_locale.ferma()
            self._piano = None
            return {"fatti": prima - len(proposte.da_fare_ai(self._prop)), "restano": len(proposte.da_fare_ai(self._prop))}
        return self._avvia("ai", f)

    def ai_scarica(self, nome):
        return self._avvia("scarica", lambda lv: ai_locale.scarica(nome, lv.avanzamento("MB"), lv.stop, self._imp))

    def ai_importa(self):
        p = self.scegli_file()
        if not p:
            return {"ok": False}
        return self._avvia("importa", lambda lv: {"modello": ai_locale.importa(p, self._imp)})

    # ------------------------------------------------------------------ piano, simulazione, esecuzione
    def piano(self):
        if not self._prop:
            return None
        sorg = {s["n"]: s["sorgente"] for s in self._schede or []}
        self._piano = piano.costruisci(self._imp, self._prop, sorg)
        xl = excel.piano(self._piano, self._imp, self._prop, self._dati("Piano.xlsx"))
        from collections import Counter
        return {"errori": self._piano["errori"], "avvisi": self._piano["avvisi"], "excel": xl,
                "operazioni": len(self._piano["operazioni"]),
                "tipi": dict(Counter(o["tipo"] for o in self._piano["operazioni"])),
                "esempi": self._piano["righe"][:300]}

    def simula(self):
        def f(lv):
            if not self._piano:
                self.piano()
            if self._piano["errori"]:
                return {"errori": self._piano["errori"]}
            r = esecuzione.esegui(self._imp, self._piano["operazioni"], False, lv.avanzamento("simulazione"))
            self._piano["simulato"] = not r["problemi"]
            return r
        return self._avvia("simula", f)

    def esegui(self, conferma):
        if conferma != "ESEGUI" or not self._piano or not self._piano.get("simulato"):
            return {"errore": "prima la simulazione senza problemi"}

        def f(lv):
            r = esecuzione.esegui(self._imp, self._piano["operazioni"], True, lv.avanzamento("esecuzione"), lv.stop)
            lv.stato.update(fase="verifica")
            r["verifica"] = esecuzione.verifica(r["log"], lv.avanzamento("verifica"))
            self._piano = None
            return r
        return self._avvia("esegui", f)

    def annulla(self, log, reale):
        return self._avvia("annulla", lambda lv: esecuzione.annulla(log, bool(reale), lv.avanzamento("annulla")))

    # ------------------------------------------------------------------ catalogo ed Excel
    def catalogo(self):
        def f(lv):
            inventario.semina_catalogo(self._imp, self._cache_inv())
            self._cbib = inventario.analizza_biblioteca(self._imp, lv.avanzamento("lettura"), lv.stop)
            if lv.stop.is_set():
                return {"interrotto": True}
            return catalogo.genera(impostazioni.cartelle(self._imp)["biblioteca"], self._cbib)
        return self._avvia("catalogo", f)

    def elenco_isbn(self):
        def f(lv):
            bib = impostazioni.cartelle(self._imp)["biblioteca"]
            return excel.elenco_isbn(self._cache_bib(), os.path.join(bib, "Elenco_libri_ISBN.xlsx"), lv.avanzamento("codici"))
        return self._avvia("elenco", f)

    def da_decidere(self):
        if not self._prop:
            return None
        return excel.da_decidere(self._prop, esecuzione.posizioni_attuali(self._imp), self._dati("Riepilogo_da_decidere.xlsx"))

    # ------------------------------------------------------------------ categorie
    def categorie_salva(self, cat):
        """cat: {nome: {"prefisso", "descrizione"}}. Le categorie gia' usate da libri in Biblioteca restano."""
        self._imp["categorie"] = {k.strip(): {"prefisso": v.get("prefisso", "").strip() or k.strip(), "descrizione": v.get("descrizione", "")}
                                 for k, v in cat.items() if k.strip()}
        impostazioni.salva(self._imp)
        self._modelli = None
        return self._imp["categorie"]


def duplicati_chiave(s):
    from .duplicati import chiave
    return chiave(s)


def verifica(uscita):
    """Autoverifica senza finestra (Biblioteca.exe --verifica <file.json>): con le impostazioni salvate fa
    l'inventario (processi in parallelo compresi) e le proposte, e scrive cosa ha trovato. Non sposta nulla."""
    import platform
    import time
    out = {"versione": __version__, "python": platform.python_version(), "risorse": os.listdir(RISORSE)}
    try:
        api = Api()
        t = time.time()
        api._cbib = inventario.analizza_biblioteca(api._imp)
        schede, cache = inventario.esegui(api._imp)
        modelli = proposte.addestra(api._imp, api._cbib)
        prop = proposte.calcola(api._imp, schede, cache, api._cbib, modelli)
        from collections import Counter
        out.update(ok=True, secondi=round(time.time() - t, 1), file=len(schede), modello=modelli["origine"],
                   decisioni=dict(Counter(p["decisione"] for p in prop)),
                   isbn=sum(1 for s in schede if s.get("isbn")), ai_locale=ai_locale.stato(api._imp),
                   esempi=[f"{p['categoria']} | {p['titolo']} | {p['autore']}" for p in prop[:5]])
    except Exception as e:  # noqa: BLE001
        out.update(ok=False, errore=traceback.format_exc())
    with open(uscita, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)


def main():
    import multiprocessing
    import webview
    multiprocessing.freeze_support()  # per l'.exe di PyInstaller (i processi dell'analisi)
    api = Api()
    api._finestra = webview.create_window("Biblioteca", os.path.join(RISORSE, "app.html"), js_api=api,
                                         width=1320, height=880, min_size=(980, 640))
    try:
        webview.start()
    finally:
        ai_locale.ferma()


if __name__ == "__main__":
    main()
