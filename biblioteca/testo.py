"""Analisi del testo dei libri: prologo, ISBN, edizione (nessuna libreria esterna).
Le funzioni lavorano sul testo gia' estratto da lettura.py: le pagine iniziali, le ultime
pagine e i metadati. Sono le stesse regole usate nel riordino della Biblioteca
(catalogo_estrai.py ed elenco_edizioni.py), staccate dalla lettura dei file.
"""
import os
import re

MAX_PAGES = 40       # pagine iniziali in cui cercare il prologo
MAX_CHARS = 2200     # lunghezza massima del prologo salvato

# ordine = priorita': un prologo vale piu' di un'introduzione
HEADINGS = [
    ("Prólogo", r"pr[oó]logo|foreword|pref[aá]cio do autor"),
    ("Prefacio", r"prefacio|pref[aá]cio|preface"),
    ("Presentación", r"presentaci[oó]n|apresenta[cç][aã]o"),
    ("Nota del autor", r"nota del autor|palabras? del autor|al lector|a los lectores|carta al lector|to the reader|note to the reader"),
    ("Introducción", r"introducci[oó]n|introdu[cç][aã]o|introduction"),
]
HEAD_RE = [(lab, re.compile(rf"^\s*(?:\d+\.?\s*)?(?:{pat})\b[\s.:]*(?:\S.{{0,60}})?$", re.I)) for lab, pat in HEADINGS]
CHAPTER_RE = re.compile(r"^\s*(cap[ií]tulo|chapter|parte|part|lecci[oó]n)\s+(\d+|[ivxl]+|uno|one|primer[oa]?)\b", re.I)
TOC_RE = re.compile(r"^\s*([ií]ndice|contenido|contents|tabla de contenido|sum[aá]rio)\s*$", re.I)
ISBN_PAGES = 15      # pagine iniziali (e 3 finali) in cui cercare l'ISBN
ISBN_LABEL_RE = re.compile(r"ISBN(?:[\s-]*1[03])?(?:\s*\([^)]{0,25}\))?[\s:.#-]*((?:97[89][\s‐-]?)?\d[\d\s‐-]{8,16}[\dXx])", re.I)
ISBN_BARE_RE = re.compile(r"(?<![\d-])(97[89][\s‐-]?\d[\d‐-]{9,15}\d)(?![\d-])")
FRONT_RE = re.compile(r"isbn|copyright|©|derechos reservados|all rights reserved|todos os direitos|impreso en|printed in|"
                      r"editorial|dep[oó]sito legal|cataloging", re.I)


def split_name(rel):
    parts = rel.replace("/", os.sep).split(os.sep)
    cat = parts[0]
    coll = os.sep.join(parts[1:-1])
    stem = os.path.splitext(parts[-1])[0]
    bits = stem.split(" - ")
    if len(bits) >= 3:
        title, author = " - ".join(bits[1:-1]), bits[-1]
    elif len(bits) == 2:
        title, author = bits[1], ""
    else:
        title, author = stem, ""
    return cat, coll, title.strip(), author.strip()


def clean(text):
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)          # parole spezzate a fine riga
    lines = [l.strip() for l in text.splitlines()]
    lines = [l for l in lines if l and not re.fullmatch(r"[\divxlc\s.\-–—]+", l, re.I)]  # numeri di pagina
    out = " ".join(lines)
    return re.sub(r"\s+", " ", out).strip()


def is_toc(lines):
    if any(TOC_RE.match(l) for l in lines[:6]):
        return True
    numbered = sum(1 for l in lines if re.search(r"(\.{3,}|\s)\d{1,3}\s*$", l))
    chapters = sum(1 for l in lines if CHAPTER_RE.match(l) or re.match(r"^\d{1,2}\s*[.)-]\s*\S", l))
    return len(lines) >= 6 and (numbered / len(lines) > 0.4 or chapters >= 4)


def is_prose(lines):
    """Testo corrente, non elenchi: almeno 400 caratteri e molte righe lunghe."""
    if sum(len(l) for l in lines) < 400:
        return False
    long_ = sum(1 for l in lines if len(l) >= 45)
    return long_ / max(1, len(lines)) >= 0.35


def isbn_ok(d):
    if len(d) == 13 and d.isdigit() and d[:3] in ("978", "979"):
        return sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(d)) % 10 == 0
    if len(d) == 10 and d[:9].isdigit() and (d[9].isdigit() or d[9] == "X"):
        return sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(d)) % 11 == 0
    return False


def to13(d):
    if len(d) == 13:
        return d
    core = "978" + d[:9]
    chk = (10 - sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(core)) % 10) % 10
    return core + str(chk)


def find_isbns(texts):
    """ISBN validi (con cifra di controllo giusta), prima quelli con l'etichetta "ISBN"."""
    found = []
    for rx in (ISBN_LABEL_RE, ISBN_BARE_RE):
        for t in texts:
            for m in rx.finditer(t):
                d = re.sub(r"[^\dX]", "", m.group(1).upper())
                for cand in (d, d[:13], d[:10]):  # numeri attaccati ad altro testo
                    if isbn_ok(cand):
                        found.append(cand)
                        break
        if found:
            break
    out, seen = [], set()
    for d in found:
        if to13(d) not in seen:
            seen.add(to13(d))
            out.append(d)
    return out[:3]


def prologo(pages):
    """Prologo (o inizio del testo) dalle pagine iniziali.
    Restituisce {"prologo", "tipo_prologo", "pagina_prologo"}; testo vuoto se non c'e' prosa."""
    res = {"prologo": "", "tipo_prologo": "", "pagina_prologo": None}
    best = None  # (priorita', pagina, riga)
    for i, p in enumerate(pages):
        lines = [l.strip() for l in p.splitlines() if l.strip()]
        if not lines or is_toc(lines):
            continue
        for j, l in enumerate(lines[:6]):
            after = lines[j + 1:] + [x.strip() for x in (pages[i + 1] if i + 1 < len(pages) else "").splitlines() if x.strip()]
            for pr, (lab, rx) in enumerate(HEAD_RE):
                if rx.match(l) and len(l) < 70 and is_prose(after[:40]):
                    if best is None or pr < best[0]:
                        best = (pr, i, j, lab)
                    break
        if best and best[0] == 0:
            break

    if best:
        _, i, j, lab = best
        lines = [l.strip() for l in pages[i].splitlines() if l.strip()][j + 1:]
        buf = "\n".join(lines)
        for k in range(i + 1, min(i + 6, len(pages))):
            nxt = [l.strip() for l in pages[k].splitlines() if l.strip()]
            if any(CHAPTER_RE.match(l) or any(rx.match(l) and len(l) < 70 for _, rx in HEAD_RE) for l in nxt[:4]):
                break
            buf += "\n" + "\n".join(nxt)
            if len(buf) > MAX_CHARS * 2:
                break
        res.update(tipo_prologo=lab, pagina_prologo=i + 1)
    else:
        # nessun prologo: primo testo vero dopo frontespizio, copyright e indice
        buf, start = "", None
        # poi un giro senza controllo di prosa (righe corte, colonne strette), poi pagine corte (schede, opuscoli)
        # ultimo giro solo per opuscoli di poche pagine: righe numerate (versetti, domande) sembrano un indice
        giri = [(True, 600, True), (False, 600, True), (False, 250, True)] + ([(False, 250, False)] if len(pages) <= 12 else [])
        for strict, min_chars, toc_check in giri:
            for i, p in enumerate(pages):
                lines = [l.strip() for l in p.splitlines() if l.strip()]
                body = clean(p)
                if len(body) < min_chars or (toc_check and is_toc(lines)) or len(FRONT_RE.findall(body)) >= 2:
                    continue
                if strict and not is_prose(lines):
                    continue
                start = i if start is None else start
                buf += "\n" + p
                if len(buf) > MAX_CHARS * 2:
                    break
            if buf:
                break
        res.update(tipo_prologo="Inizio del testo" if buf else "", pagina_prologo=(start + 1) if start is not None else None)
    text = clean(buf)
    if text[:1].islower():  # comincia a meta' frase: si parte dalla frase successiva
        m = re.search(r"[.!?»”\"]\s+(?=[¿¡«“\"A-ZÁÉÍÓÚÑ])", text[:600])
        if m:
            text = text[m.end():]
    if len(text) > MAX_CHARS:
        cut = text[:MAX_CHARS]
        dot = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
        text = (cut[:dot + 1] if dot > MAX_CHARS * 0.6 else cut.rsplit(" ", 1)[0]) + " …"
    res["prologo"] = text
    return res

ORD_WORDS = {
    "primera": 1, "primer": 1, "segunda": 2, "tercera": 3, "cuarta": 4, "quinta": 5, "sexta": 6,
    "septima": 7, "octava": 8, "novena": 9, "decima": 10, "undecima": 11, "duodecima": 12,
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7,
    "eighth": 8, "ninth": 9, "tenth": 10,
    "primeira": 1, "terceira": 3, "quarta": 4, "setima": 7, "oitava": 8, "nona": 9,
}
ORD_PAT = (r"primera|primer|segunda|tercera|cuarta|quinta|sexta|s[eé]ptima|octava|novena|d[eé]cima|"
           r"und[eé]cima|duod[eé]cima|first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|"
           r"primeira|terceira|quarta|s[eé]tima|oitava|nona")
NUM_PAT = r"(\d{1,2})\s?(?:ª|º|°|\.ª|\.º|a\.?|o\.?|st|nd|rd|th)"
ED_PAT = r"edici[oó]n|edition|edi[cç][aã]o|ed\."
QUAL_PAT = (r"revisada|ampliada|actualizada|corregida|aumentada|conmemorativa|revised|expanded|updated|"
            r"enlarged|anniversary|revista|atualizada")
ORD_RE = re.compile(rf"\b(?:({ORD_PAT})|{NUM_PAT})\s+(?:{ED_PAT})(?:\s+(?:y\s+|e\s+|and\s+)?({QUAL_PAT}))?", re.I)
QUAL_RE = re.compile(rf"\b(?:(?:{ED_PAT})\s+({QUAL_PAT})|({QUAL_PAT})\s+(?:{ED_PAT}))", re.I)
YEAR_RE = re.compile(r"\b(1[5-9]\d\d|20[0-4]\d)\b")
# edizioni di altro: le Bibbie citate nei crediti ("La Biblia Dios Habla Hoy, Tercera edición © SBU")
BIBLE_RE = re.compile(r"biblia|bible|b[ií]blic|lockman|testament|reina[- ]valera|versi[oó]n|vers[aã]o|"
                      r"dios habla hoy|\b(?:nvi|ntv|dhh|lbla|nbla|rvr\d*|rv\d\d|kjv|niv|esv|rsv)\b", re.I)
BIBLE_AFTER_RE = re.compile(r"sociedades? b[ií]blicas?|bible societ|lockman|consejo nacional de las iglesias|"
                            r"national council of the churches|divisi[oó]n de educaci[oó]n|division of christian", re.I)
TRAIL_RE = re.compile(r"(?:[\s\[(©·•—–?-]|copyright|\b\d{4}\b)+$", re.I)
# frasi nel testo ("colaboró en la primera edición del diccionario")
ARTICLE_RE = re.compile(r"\b(la|una|esta|su|the|a|this|its|da|uma|sua|en|in|em)\s*$", re.I)


def other_edition(flat, start):
    before = flat[max(0, start - 120):start]
    before = re.split(r"[.;]\s|\bISBN\b", before, flags=re.I)[-1]  # solo la stessa frase
    if BIBLE_AFTER_RE.search(flat[start:start + 70]):
        return True
    # la Bibbia conta solo se l'edizione e' la sua: subito dopo il nome o dopo una virgola
    # ("Dios Habla Hoy © Tercera edición", "de la Biblia, copyright 1952 [2ª edición"),
    # non "Centro de Literatura Bíblica ... Primera edición"
    core = TRAIL_RE.sub("", before)
    bible = BIBLE_RE.search(before) and (core.endswith(",") or BIBLE_RE.search(core[-25:]))
    return bool(bible or ARTICLE_RE.search(before))


def strip_accents(s):
    return s.translate(str.maketrans("áéíóúÁÉÍÓÚ", "aeiouAEIOU"))


def find_edition(texts):
    """(edizione normalizzata, testo trovato) oppure ("", "")."""
    best = None  # (numero, qualifica, anno, testo)
    qual_only = None
    for t in texts:
        if not FRONT_RE.search(t):  # solo pagine di copyright / colophon
            continue
        flat = re.sub(r"\s+", " ", t)
        for m in ORD_RE.finditer(flat):
            num = ORD_WORDS.get(strip_accents(m.group(1).lower())) if m.group(1) else int(m.group(2))
            if not num or num > 60 or other_edition(flat, m.start()):
                continue
            ym = YEAR_RE.search(flat[m.end():m.end() + 40])
            year = ym.group(1) if ym else ""
            raw = flat[m.start():ym.end() + m.end() if ym else m.end()].strip(" ,.:;-")
            cand = (num, (m.group(3) or "").lower(), year, raw[:90])
            if best is None or cand[0] > best[0] or (cand[0] == best[0] and cand[2] > best[2]):
                best = cand
        if qual_only is None:
            for q in QUAL_RE.finditer(flat):
                if not other_edition(flat, q.start()):
                    qual_only = ((q.group(1) or q.group(2)).lower(), q.group(0))
                    break
    if best:
        num, qual, year, raw = best
        ed = f"{num}ª ed."
        if qual:
            ed += f" {qual}"
        if year:
            ed += f" ({year})"
        return ed, raw
    if qual_only:
        return f"ed. {qual_only[0]}", qual_only[1][:90]
    return "", ""


def analizza(pages, tail, meta):
    """Tutto quello che serve al catalogo da un libro gia' letto.
    pages: testo delle pagine iniziali (fino a MAX_PAGES); tail: ultime pagine; meta: valori dei metadati."""
    res = {"isbn": find_isbns(pages[:ISBN_PAGES] + tail + meta), "testo": "ok"}
    ed_texts = pages[:ISBN_PAGES] + tail + [" ISBN " + m for m in meta]
    res["edizione"], res["testo_edizione"] = find_edition(ed_texts)
    if sum(len(p.strip()) for p in pages) < 300:
        res.update(testo="scansione", prologo="", tipo_prologo="", pagina_prologo=None)
        return res
    res.update(prologo(pages))
    if not res["prologo"]:
        res["testo"] = "poco"
    return res
