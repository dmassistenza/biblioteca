"""Lettura dei libri (sola lettura): testo delle pagine, metadati, numero di pagine.
Solo librerie con licenza libera, per poter distribuire il programma:
- PDF con pypdfium2 (Apache-2.0 / BSD-3), il motore PDF di Chrome;
- EPUB con la libreria standard di Python (zip + XML + HTML), anche se il file non ha estensione;
- MOBI e AZW3 non vengono letti (servirebbe Calibre): risultano "non_leggibile".
Ogni lettore restituisce lo stesso dizionario, cosi' l'analisi (testo.py) non dipende dal formato.
"""
import hashlib
import html
import os
import posixpath
import re
import zipfile
from html.parser import HTMLParser
from xml.etree import ElementTree as ET

from .testo import ISBN_PAGES, MAX_PAGES

TAIL_PAGES = 3


def vuoto():
    return {"formato": "", "pagine": 0, "iniziali": [], "finali": [], "meta": {}, "errore": "", "stato": "ok"}


def sha256(path, buf=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(buf), b""):
            h.update(b)
    return h.hexdigest()


def is_zip_without_ext(path):
    if os.path.splitext(path)[1]:
        return False
    try:
        with open(path, "rb") as f:
            return f.read(4) == b"PK\x03\x04"
    except OSError:
        return False


def formato(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".pdf", ".epub", ".mobi", ".azw3", ".azw"):
        return ext[1:]
    if is_zip_without_ext(path):
        return "epub"
    return ""


def leggi(path, max_pages=MAX_PAGES):
    fmt = formato(path)
    if fmt == "pdf":
        return leggi_pdf(path, max_pages)
    if fmt == "epub":
        return leggi_epub(path, max_pages)
    res = vuoto()
    res.update(formato=fmt, stato="non_leggibile" if fmt else "non_libro")
    return res


# ---------------------------------------------------------------- PDF
def leggi_pdf(path, max_pages):
    import pypdfium2 as pdfium
    res = vuoto()
    res["formato"] = "pdf"
    try:
        pdf = pdfium.PdfDocument(path)
    except pdfium.PdfiumError as e:
        msg = str(e)
        if "password" in msg.lower():
            res.update(stato="protetto", errore=msg[:200])
            return res
        return leggi_pdf_riserva(path, max_pages, msg)
    except Exception as e:  # noqa: BLE001
        res.update(stato="errore", errore=str(e)[:200])
        return res
    try:
        n = len(pdf)
        res["pagine"] = n
        try:
            res["meta"] = {k: v for k, v in pdf.get_metadata_dict(skip_empty=True).items()}
        except Exception:  # noqa: BLE001
            pass

        def text(i):
            try:
                page = pdf[i]
                tp = page.get_textpage()
                t = tp.get_text_range()
                tp.close()
                page.close()
                return t.replace("\r\n", "\n").replace("\r", "\n")
            except Exception:  # noqa: BLE001
                return ""

        first = min(max_pages, n)
        res["iniziali"] = [text(i) for i in range(first)]
        res["finali"] = [text(i) for i in range(max(first, n - TAIL_PAGES), n)]
    finally:
        pdf.close()
    return res


def leggi_pdf_riserva(path, max_pages, primo_errore):
    """PDF danneggiati che PDFium rifiuta ("Data format error"): pypdf (BSD-3) li ricostruisce spesso."""
    res = vuoto()
    res["formato"] = "pdf"
    try:
        from pypdf import PdfReader
        r = PdfReader(path, strict=False)
        if r.is_encrypted:
            res.update(stato="protetto", errore="password")
            return res
        n = len(r.pages)
        res["pagine"] = n
        res["meta"] = {k.lstrip("/"): str(v) for k, v in (r.metadata or {}).items() if v}

        def text(i):
            try:
                return r.pages[i].extract_text() or ""
            except Exception:  # noqa: BLE001
                return ""

        first = min(max_pages, n)
        res["iniziali"] = [text(i) for i in range(first)]
        res["finali"] = [text(i) for i in range(max(first, n - TAIL_PAGES), n)]
        res["nota"] = "letto con pypdf (PDF danneggiato)"
    except Exception as e:  # noqa: BLE001
        res.update(stato="errore", errore=(primo_errore + " / " + str(e))[:200])
    return res


# ---------------------------------------------------------------- EPUB
class _Html2Text(HTMLParser):
    BLOCK = {"p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "section", "blockquote", "title"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self.skip += 1
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head"):
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)

    def text(self):
        t = "".join(self.out)
        t = re.sub(r"[ \t\xa0]+", " ", t)
        return re.sub(r"\n\s*\n+", "\n", t).strip()


def _html_text(raw):
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            s = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    p = _Html2Text()
    try:
        p.feed(s)
    except Exception:  # noqa: BLE001
        return html.unescape(re.sub(r"<[^>]+>", " ", s))
    return p.text()


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def leggi_epub(path, max_pages):
    """Ogni documento dello "spine" (capitolo) conta come una pagina: i titoli dei capitoli
    stanno in cima, come nelle pagine di un PDF, e la ricerca del prologo funziona uguale."""
    res = vuoto()
    res["formato"] = "epub"
    try:
        z = zipfile.ZipFile(path)
    except Exception as e:  # noqa: BLE001
        res.update(stato="errore", errore=str(e)[:200])
        return res
    with z:
        try:
            cont = ET.fromstring(z.read("META-INF/container.xml"))
            opf_path = next(el.get("full-path") for el in cont.iter() if _local(el.tag) == "rootfile")
            opf = ET.fromstring(z.read(opf_path))
        except Exception as e:  # noqa: BLE001
            res.update(stato="errore", errore=("container/opf: " + str(e))[:200])
            return res
        base = posixpath.dirname(opf_path)
        meta, manifest, spine = {}, {}, []
        for el in opf.iter():
            tag = _local(el.tag)
            if tag in ("title", "creator", "publisher", "identifier", "language", "date", "subject", "description"):
                if el.text and el.text.strip():
                    key = {"creator": "author"}.get(tag, tag)
                    meta[key] = (meta[key] + "; " if key in meta else "") + el.text.strip()
            elif tag == "item":
                manifest[el.get("id")] = (el.get("href"), el.get("media-type", ""))
            elif tag == "itemref":
                spine.append(el.get("idref"))
        res["meta"] = meta
        docs = []
        for idref in spine:
            href, mt = manifest.get(idref, (None, ""))
            if href and ("html" in mt or href.lower().endswith((".html", ".xhtml", ".htm"))):
                docs.append(posixpath.normpath(posixpath.join(base, html.unescape(href).split("#")[0])))
        texts = []
        for d in docs:
            try:
                texts.append(_html_text(z.read(d)))
            except KeyError:
                try:  # nomi codificati in modo diverso nello zip
                    texts.append(_html_text(z.read(d.replace("%20", " "))))
                except KeyError:
                    texts.append("")
        pages = _impagina(texts)
        res["pagine"] = len(pages)
        res["iniziali"] = pages[:max_pages]
        res["finali"] = pages[max(max_pages, len(pages) - TAIL_PAGES):]
        if sum(len(t) for t in texts) < 300:
            res["stato"] = "solo_immagini"
    return res


EPUB_PAGE = 2200  # caratteri per "pagina", circa una pagina di libro


def _impagina(docs):
    """Divide i capitoli in pagine di circa EPUB_PAGE caratteri, andando a capo tra le righe.
    Ogni capitolo comincia una pagina nuova (come in un libro), cosi' il titolo resta in cima."""
    pages = []
    for d in docs:
        cur, size = [], 0
        for line in d.split("\n"):
            if size and size + len(line) > EPUB_PAGE:
                pages.append("\n".join(cur))
                cur, size = [], 0
            cur.append(line)
            size += len(line) + 1
        if cur and size:
            pages.append("\n".join(cur))
    return pages


def copertina(path, larghezza=360):
    """Immagine della prima pagina (PDF) o della copertina (EPUB) in PNG, per l'anteprima. b"" se non c'e'."""
    import io
    from PIL import Image
    fmt = formato(path)
    try:
        if fmt == "pdf":
            import pypdfium2 as pdfium
            pdf = pdfium.PdfDocument(path)
            try:
                page = pdf[0]
                w = page.get_width()
                img = page.render(scale=larghezza / w if w else 1).to_pil()
                page.close()
            finally:
                pdf.close()
        elif fmt == "epub":
            with zipfile.ZipFile(path) as z:
                cont = ET.fromstring(z.read("META-INF/container.xml"))
                opf_path = next(el.get("full-path") for el in cont.iter() if _local(el.tag) == "rootfile")
                opf = ET.fromstring(z.read(opf_path))
                base = posixpath.dirname(opf_path)
                cover_id = next((el.get("content") for el in opf.iter() if _local(el.tag) == "meta" and el.get("name") == "cover"), None)
                items = [el for el in opf.iter() if _local(el.tag) == "item"]
                cand = [el for el in items if "cover-image" in (el.get("properties") or "")] + \
                       [el for el in items if el.get("id") == cover_id] + \
                       [el for el in items if (el.get("media-type") or "").startswith("image/") and "cover" in (el.get("href") or "").lower()] + \
                       [el for el in items if (el.get("media-type") or "").startswith("image/")]
                if not cand:
                    return b""
                href = posixpath.normpath(posixpath.join(base, html.unescape(cand[0].get("href"))))
                img = Image.open(io.BytesIO(z.read(href)))
                img.thumbnail((larghezza, larghezza * 2))
        else:
            return b""
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "PNG", optimize=True)
        return buf.getvalue()
    except Exception:  # noqa: BLE001  anteprima facoltativa: un file strano non deve dare errori
        return b""


def analizza_file(path):
    """Lettura + analisi: il risultato completo per un libro."""
    from .testo import analizza
    r = leggi(path)
    out = {"formato": r["formato"], "pagine": r["pagine"], "stato": r["stato"], "errore": r["errore"], "meta": r["meta"]}
    if r["stato"] in ("ok", "solo_immagini"):
        out.update(analizza(r["iniziali"], r["finali"], [str(v) for v in r["meta"].values() if v]))
        out["anteprima"] = "\n".join(r["iniziali"][:ISBN_PAGES])[:6000]
        out["prime_pagine"] = [p[:3000] for p in r["iniziali"][:6]]  # per la pagina del titolo (nomi.py)
    return out
