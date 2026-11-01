"""I file Excel del programma (openpyxl, licenza MIT):
- inventario: Riepilogo, Inventario, Duplicati_identici, Senza_testo, Errori;
- piano: Riepilogo, Categorie_prefissi, Piano, Avvisi;
- elenco dei libri con ISBN e codice a barre EAN-13 verificato;
- riepilogo delle cose da decidere, con la posizione attuale dei libri ricostruita dai log.
"""
import os
import re
import tempfile
from collections import Counter

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from . import barcode, duplicati
from .testo import split_name, to13

ILLEGALI = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
BLU = PatternFill("solid", fgColor="1F4E78")


def _intesta(ws, cols, widths):
    ws.append(cols)
    for i, c in enumerate(cols, 1):
        cell = ws.cell(1, i)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = BLU
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = widths.get(c, 18)


def foglio(wb, titolo, righe, cols, widths=None):
    ws = wb.create_sheet(titolo)
    _intesta(ws, cols, widths or {})
    for r in righe:
        vals = [r.get(c, "") for c in cols]
        ws.append([ILLEGALI.sub("", v) if isinstance(v, str) else (", ".join(map(str, v)) if isinstance(v, list) else v)
                   for v in vals])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    return ws


def _salva(wb, path):
    tmp = path + ".tmp.xlsx"
    wb.save(tmp)
    os.replace(tmp, path)
    return path


def inventario(schede, path):
    for s in schede:
        s["MB"] = round((s.get("byte") or 0) / 1048576, 2)
        s["isbn_13"] = ", ".join(to13(i) for i in s.get("isbn") or [])
        m = s.get("meta") or {}
        s["meta_titolo"] = m.get("Title") or m.get("title") or ""
        s["meta_autore"] = m.get("Author") or m.get("author") or ""
    gruppi = duplicati.identici(schede)
    dup = []
    for gid, g in enumerate(gruppi.values(), 1):
        for i, s in enumerate(g):
            dup.append({**s, "gruppo": gid, "azione": "TENERE" if i == 0 else "-> _duplicati"})
    libri = [s for s in schede if s["tipo"] == "libro"]
    senza = [s for s in libri if s.get("testo") in ("scansione", "poco")]
    errori = [s for s in schede if s.get("errore") or s["tipo"] in ("non_leggibile", "vuoto") or s.get("stato") == "protetto"]
    wb = Workbook()
    ws = wb.active
    ws.title = "Riepilogo"
    righe = [("File trovati", len(schede)), ("Libri", len(libri)),
             ("Dimensione totale (GB)", round(sum(s.get("byte") or 0 for s in schede) / 1024 ** 3, 2)),
             ("Gruppi di copie identiche (SHA-256)", len(gruppi)),
             ("Copie in eccesso (vanno in _duplicati)", len(dup) - len(gruppi)),
             ("Libri senza testo o con poco testo (scansioni)", len(senza)),
             ("Protetti da password", sum(1 for s in libri if s.get("stato") == "protetto")),
             ("File con errori o non leggibili", len(errori)), ("", ""), ("Lingua stimata", "")]
    righe += [(f"  {k or '(non rilevata)'}", v) for k, v in Counter(s.get("lingua", "") for s in libri).most_common()]
    righe += [("", ""), ("Formati", "")]
    righe += [(f"  {k or '(nessuna estensione)'}", v) for k, v in Counter(s["estensione"] for s in schede).most_common()]
    for r in righe:
        ws.append(r)
    ws.column_dimensions["A"].width = 55
    ws.column_dimensions["B"].width = 14
    w = {"n": 7, "cartella": 30, "file": 60, "MB": 8, "pagine": 8, "percorso": 70, "meta_titolo": 40, "meta_autore": 25,
         "sha256": 20, "errore": 50, "edizione": 18, "isbn_13": 18}
    foglio(wb, "Inventario", schede, ["n", "cartella", "file", "tipo", "formato", "MB", "pagine", "testo", "lingua",
                                     "meta_titolo", "meta_autore", "isbn_13", "edizione", "stato", "errore", "sha256", "percorso"], w)
    foglio(wb, "Duplicati_identici", dup, ["gruppo", "azione", "cartella", "file", "MB", "testo", "sha256", "percorso"], w)
    foglio(wb, "Senza_testo", senza, ["n", "cartella", "file", "MB", "pagine", "testo", "percorso"], w)
    foglio(wb, "Errori", errori, ["n", "cartella", "file", "tipo", "stato", "errore", "percorso"], w)
    return _salva(wb, path)


def piano(risultato, imp, proposte, path):
    righe = risultato["righe"]
    wb = Workbook()
    ws = wb.active
    ws.title = "Riepilogo"
    cnt = Counter(r["decisione"] for r in righe)
    for k, v in [("Libri da importare", cnt["IMPORTA"]), ("Già in Biblioteca (restano dove sono)", cnt["GIA_IN_BIBLIOTECA"]),
                 ("Copie identiche (vanno in _duplicati)", cnt["DUPLICATO"]),
                 ("Probabili doppioni (restano dove sono)", cnt["DOPPIONE_PROBABILE"]),
                 ("Non importati (scelta o file non leggibile)", cnt["NON_IMPORTARE"]),
                 ("File che non sono libri (vanno in _altri_file)", cnt["ALTRI_FILE"]),
                 ("Operazioni", len(risultato["operazioni"])), ("Errori da correggere", len(risultato["errori"])),
                 ("Avvisi", len(risultato["avvisi"]))]:
        ws.append((k, v))
    ws.append(("", ""))
    for c, v in Counter(r["categoria"] for r in righe if r["decisione"] == "IMPORTA").most_common():
        ws.append((f"  in {c}", v))
    ws.column_dimensions["A"].width = 55
    cats = [{"categoria": k, "prefisso": v["prefisso"], "descrizione": v["descrizione"],
             "libri da importare": cnt_c} for k, v in imp["categorie"].items()
            for cnt_c in [sum(1 for r in righe if r["decisione"] == "IMPORTA" and r["categoria"] == k)]]
    foglio(wb, "Categorie_prefissi", cats, ["categoria", "prefisso", "descrizione", "libri da importare"],
           {"categoria": 32, "prefisso": 18, "descrizione": 70})
    w = {"n": 6, "decisione": 20, "motivo": 40, "file_attuale": 55, "nuovo_nome": 80, "categoria": 26, "collezione": 30,
         "titolo": 50, "autore": 30, "nota": 50, "segnalazioni": 30, "destinazione": 90}
    foglio(wb, "Piano", righe, list(w), w)
    foglio(wb, "Avvisi", [{"tipo": "ERRORE", "testo": e} for e in risultato["errori"]] +
           [{"tipo": "avviso", "testo": a} for a in risultato["avvisi"]], ["tipo", "testo"], {"tipo": 10, "testo": 120})
    return _salva(wb, path)


def elenco_isbn(cache, path, avanzamento=None):
    """Elenco dei libri della Biblioteca con edizione, ISBN e codice a barre. Ogni codice viene
    riletto dai pixel: se uno solo non torna, l'Excel non viene scritto."""
    righe = []
    for rel, v in cache.items():
        c, k, t, a = split_name(rel)
        isbns = v.get("isbn") or []
        righe.append({"cat": c, "coll": k, "tit": t, "aut": a, "ed": v.get("edizione") or "",
                      "ed_txt": v.get("testo_edizione") or "", "i13": to13(isbns[0]) if isbns else "",
                      "istamp": isbns[0] if isbns else "", "altri": ", ".join(to13(x) for x in isbns[1:]),
                      "fmt": os.path.splitext(rel)[1][1:].upper() or "EPUB", "pag": v.get("pagine") or "", "rel": rel})
    righe.sort(key=lambda r: (r["cat"].casefold(), r["coll"].casefold(), r["tit"].casefold()))
    png_dir = tempfile.mkdtemp(prefix="biblioteca_barcode_")
    sbagliati = []
    con = [r for r in righe if r["i13"]]
    for i, r in enumerate(con, 1):
        r["png"] = os.path.join(png_dir, r["i13"] + ".png")
        barcode.draw_barcode(r["i13"], r["png"])
        if barcode.decode_barcode(r["png"]) != r["i13"]:
            sbagliati.append(r["i13"])
        if avanzamento:
            avanzamento(i, len(con), r["tit"])
    if sbagliati:
        raise RuntimeError("codici a barre riletti male: " + ", ".join(sbagliati[:10]))
    wb = Workbook()
    ws = wb.active
    ws.title = "Libri"
    head = ["N", "Categoria", "Collezione", "Titolo", "Autore", "Edizione", "Edizione (testo nel libro)",
            "ISBN-13", "ISBN stampato", "Altri ISBN", "Codice a barre", "Formato", "Pagine", "File"]
    widths = [6, 22, 22, 50, 30, 18, 34, 17, 15, 22, 27, 9, 8, 60]
    _intesta(ws, head, dict(zip(head, widths)))
    ws.row_dimensions[1].height = 30
    top = Alignment(vertical="center", wrap_text=True)
    for n, r in enumerate(righe, 1):
        ws.append([n, r["cat"], r["coll"], r["tit"], r["aut"], r["ed"], ILLEGALI.sub("", r["ed_txt"]), r["i13"],
                   r["istamp"], r["altri"], "", r["fmt"], r["pag"], r["rel"]])
        rr = n + 1
        for c in range(1, len(head) + 1):
            ws.cell(rr, c).alignment = top
        for c in (8, 9):
            ws.cell(rr, c).number_format = "@"
        if r["i13"]:
            img = XLImage(r["png"])
            img.width, img.height = 170, 91  # mostrato a meta', il PNG resta a piena risoluzione
            ws.add_image(img, f"K{rr}")
            ws.row_dimensions[rr].height = 72
        else:
            ws.row_dimensions[rr].height = 30
    ws.freeze_panes = "E2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(head))}{len(righe) + 1}"
    ws.print_title_rows = "1:1"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    s = wb.create_sheet("Riepilogo")
    for col, wd in zip("ABCD", (34, 12, 14, 14)):
        s.column_dimensions[col].width = wd
    s.append(["Riepilogo", "Libri", "Con ISBN", "Con edizione"])
    s.append(["Totale", len(righe), len(con), sum(1 for r in righe if r["ed"])])
    s.append([])
    s.append(["Categoria", "Libri", "Con ISBN", "Con edizione"])
    for c in sorted({r["cat"] for r in righe}, key=str.casefold):
        sub = [r for r in righe if r["cat"] == c]
        s.append([c, len(sub), sum(1 for r in sub if r["i13"]), sum(1 for r in sub if r["ed"])])
    for rr in (1, 4):
        for c in range(1, 5):
            s.cell(rr, c).font = Font(bold=True, color="FFFFFF")
            s.cell(rr, c).fill = BLU
    s.append([])
    s.append(["Note"])
    s.cell(s.max_row, 1).font = Font(bold=True)
    for t in ["Titolo e autore vengono dal nome del file; categoria e collezione dalle cartelle.",
              "L'ISBN è quello trovato nelle prime pagine, nelle ultime o nei metadati del libro.",
              "Il codice a barre è l'EAN-13 dell'ISBN-13 (gli ISBN-10 sono convertiti): si legge con",
              "qualsiasi lettore di codici a barre o app del telefono. Ogni codice è stato riletto e verificato.",
              "L'edizione viene dalla pagina di copyright; se ce ne sono più d'una è indicata la più recente.",
              "Edizione vuota = non scritta nel libro (o libro scansionato senza testo)."]:
        s.append([t])
    out = _salva(wb, path)
    return {"file": out, "libri": len(righe), "con_isbn": len(con), "con_edizione": sum(1 for r in righe if r["ed"])}


def da_decidere(proposte, posizioni, path):
    """Libri segnalati (doppioni probabili, autore mancante, senza testo, da controllare) e dove sono ora."""
    def riga(p):
        pos = posizioni.get(p.get("sha256"), p["percorso"])
        return {"n": p["n"], "decisione": p["decisione"], "categoria": p["categoria"], "collezione": p["collezione"],
                "titolo": p["titolo"], "autore": p["autore"], "motivo": p["motivo"], "nota": p["nota"],
                "simili": "\n".join(p.get("simili") or []), "percorso_attuale": pos,
                "esiste": "sì" if os.path.isfile(pos) else "NO"}
    fogli = [("Probabili doppioni", "probabile doppione", "Libri che sembrano già presenti. Decidere quale tenere."),
             ("Titolo simile", "titolo simile in Biblioteca", "Titolo simile a un libro della Biblioteca: controllare."),
             ("Autore mancante", "autore mancante", "Autore non ricavabile con certezza."),
             ("Senza testo (OCR)", "senza testo", "Scansioni senza testo ricercabile: candidati all'OCR."),
             ("Da controllare", "da controllare", "File danneggiati o protetti, libri 'No Cristiano'.")]
    wb = Workbook()
    wb.remove(wb.active)
    cols = ["n", "decisione", "categoria", "collezione", "titolo", "autore", "motivo", "nota", "simili", "percorso_attuale", "esiste"]
    w = {"n": 6, "decisione": 18, "categoria": 24, "collezione": 24, "titolo": 50, "autore": 30, "motivo": 40,
         "nota": 50, "simili": 70, "percorso_attuale": 90, "esiste": 7}
    info = []
    for titolo, flag, desc in fogli:
        righe = [riga(p) for p in proposte if flag in p["flags"]]
        info.append({"foglio": titolo, "righe": len(righe), "cosa contiene": desc})
        foglio(wb, titolo, righe, cols, w)
    leggimi = foglio(wb, "Leggimi", info, ["foglio", "righe", "cosa contiene"], {"foglio": 24, "righe": 8, "cosa contiene": 100})
    wb.move_sheet(leggimi, offset=-len(fogli))
    return _salva(wb, path)
