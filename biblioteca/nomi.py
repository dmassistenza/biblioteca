"""Proposte di titolo, autore e numero di volume per un libro non ancora ordinato.
Candidati: metadati del file (se non sono spazzatura), pezzi del nome del file ripulito, righe
della pagina del titolo. Vince il candidato le cui parole compaiono nelle prime pagine del libro:
cosi' un nome di file in inglese non batte il titolo spagnolo stampato nel libro.
Poi: accenti recuperati dal testo ("cntico" -> "cántico"), maiuscole come nella Biblioteca
("Conquistemos Las Puertas" -> "Conquistemos las puertas", ma "Dios", "Espíritu Santo" restano).
"""
import re
import unicodedata

JUNK_META = re.compile(r"^(untitled|sin t[ií]tulo|microsoft word|documento?\d*|doc\d*|libro\d*|book\d*|admin|windows(?: user)?|"
                       r"user|usuario|owner|propietario|pc|hp|dell|lenovo|acer|asus|colossus|unknown|anonymous|"
                       r"desconocido|calibre|abc|www\.|http|\d+$)", re.I)
JUNK_NAME = re.compile(r"\((?:z-?lib(?:rary)?(?:\.org)?|spanish edition|edici[oó]n en espa[nñ]ol|english edition|"
                       r"portuguese edition|ebook|pdf|epub)\)|\[[^\]]*\]|z-?library|z-lib\.org|libgen(?:\.\w+)?|"
                       r"\bebook\b|\bpdfcoffee\b|\bdokumen\.pub\b|-spanish\b|\bspanish\b|\.bin\b|\.qxd\b|\.indd\b", re.I)
ISBN_IN_NAME = re.compile(r"\b97[89][\d-]{10,14}\b|\b\d{9}[\dXx]\b")
VOL_RE = re.compile(r"\b(?:tomo|vol(?:umen|ume|\.)?|libro|parte|part|book|n[ºo°]\.?|#)\s*(\d{1,3}|[ivxl]{1,6})\b", re.I)
ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10,
         "xi": 11, "xii": 12, "xiii": 13, "xiv": 14, "xv": 15}
NOT_TITLE = re.compile(r"isbn|copyright|©|derechos|reserved|editorial|publicado|published|impreso|printed|"
                       r"traducci[oó]n|translated|www\.|@|\bpor\b\s*$|^\s*by\s*$|^\d+$|^[ivxlc]+$|"
                       r"cap[ií]tulo|chapter|contenido|[ií]ndice|contents|dedicatoria|dedicado", re.I)
SMALL = {"de", "del", "la", "las", "el", "los", "y", "e", "o", "u", "en", "a", "al", "con", "por", "para", "sin",
         "sobre", "un", "una", "of", "the", "and", "in", "to", "for", "da", "do", "das", "dos", "que", "su", "sus", "mi", "tu"}


def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"[^a-z0-9ñ]+", " ", s).strip()


def pulisci(s):
    s = JUNK_NAME.sub(" ", s)
    s = ISBN_IN_NAME.sub(" ", s)
    s = re.sub(r"(?<=[a-záéíóúñ])_(?=[A-ZÁÉÍÓÚÑ])", " - ", s) if s.count("_") == 1 else s  # "Randy_Frazee The_..."
    s = re.sub(r"[_+]+", " ", s)
    s = re.sub(r"^[#\-–—.\s]+|[#\-–—.\s]+$", "", s)
    s = re.sub(r"\s*-\s*-+\s*", " - ", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip(" -–—.,;")


def meta_buono(v):
    v = (v or "").strip()
    return len(v) >= 3 and not JUNK_META.match(v) and not re.search(r"\.(docx?|pdf|indd|qxd|rtf|txt|bin)\b", v, re.I)


def volume(*testi):
    for t in testi:
        m = VOL_RE.search(t or "")
        if m:
            v = m.group(1).lower()
            return int(v) if v.isdigit() else ROMAN.get(v)
    return None


class Stile:
    """Quello che si impara dalla Biblioteca gia' ordinata: autori noti e parole che restano maiuscole."""

    def __init__(self, titoli=(), autori=()):
        self.autori = {norm(a) for a in autori if a}
        maiu, tot = {}, {}
        for t in titoli:
            ws = re.findall(r"[\wáéíóúñü]+", t)
            for i, w in enumerate(ws[1:], 1):  # la prima parola e' sempre maiuscola: non conta
                k = w.lower()
                tot[k] = tot.get(k, 0) + 1
                if w[:1].isupper():
                    maiu[k] = maiu.get(k, 0) + 1
        self.maiuscole = {k for k, n in maiu.items() if n / tot[k] >= 0.6}

    def maiuscole_come_biblioteca(self, t):
        ws = t.split(" ")
        out = []
        start = True
        for w in ws:
            core = re.sub(r"^[¿¡(\"'«“]+|[)\"'»”.,;:!?]+$", "", w)
            low = core.lower()
            if start:
                nw = w.replace(core, core[:1].upper() + core[1:].lower() if core.isupper() or core.istitle() else core, 1)
            elif re.fullmatch(r"[IVXLC]+|\d+\w*", core) or (core.isupper() and len(core) <= 4 and len(core) > 1 and not t.isupper()):
                nw = w  # numeri romani, sigle (NVI, EUA)
            elif low in self.maiuscole:
                nw = w.replace(core, core[:1].upper() + core[1:].lower(), 1)
            else:
                nw = w.replace(core, low, 1)
            out.append(nw)
            # dopo la virgola comincia il sottotitolo: maiuscola, come nei nomi della Biblioteca
            start = w.endswith((",", ".", "?", "!", ":"))
        return " ".join(out)


def accenti_dal_testo(t, testo):
    """Rimette accenti e lettere perse ("cntico" -> "cántico") cercando la parola nel testo del libro."""
    if not testo:
        return t
    forme = {}
    for w in re.findall(r"[A-Za-zÁÉÍÓÚÑÜáéíóúñü]{3,}", testo[:20000]):
        f = forme.setdefault(norm(w), {})
        f[w.lower()] = f.get(w.lower(), 0) + 1
    # la forma piu' frequente nel libro ("esta" e "está" esistono entrambe: vince quella usata di piu')
    voc = {k: max(f, key=f.get) for k, f in forme.items()}

    by_len = {}
    for k, v in voc.items():
        by_len.setdefault(len(k), []).append((k, v))

    def fix(m):
        w = m.group(0)
        n = norm(w)
        if any(ch in w for ch in "áéíóúñÁÉÍÓÚÑ"):
            return w
        cand = voc.get(n)
        if cand is None and len(n) >= 4:
            # una lettera accentata sparita dal nome del file: "cntico" -> "cántico" (una lettera in piu' nel testo)
            for k, v in by_len.get(len(n) + 1, ()):
                if any(ch in v for ch in "áéíóúñÁÉÍÓÚÑ") and any(k[:i] + k[i + 1:] == n for i in range(len(k))):
                    cand = v
                    break
        if not cand or cand.lower() == w.lower():
            return w
        if w.isupper():
            return cand.upper()
        if w[:1].isupper():
            return cand[:1].upper() + cand[1:].lower()
        return cand.lower()

    return re.sub(r"[A-Za-zñÑ]{3,}", fix, t)


def presente(cand, testo_n):
    """Quota delle parole del candidato che compaiono nelle prime pagine (testo normalizzato)."""
    ws = [w for w in norm(cand).split() if len(w) > 2 and w not in SMALL]
    if not ws:
        return 0.0
    return sum(1 for w in ws if f" {w} " in testo_n) / len(ws)


def righe_frontespizio(pagine):
    """Righe candidate dalla pagina del titolo: una delle prime pagine con poche righe brevi."""
    out = []
    for p in pagine[:5]:
        lines = [l.strip() for l in p.splitlines() if l.strip()]
        if not 1 <= len(lines) <= 14:
            continue
        good = [l for l in lines if 3 <= len(l) <= 90 and not NOT_TITLE.search(l) and re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]{3}", l)]
        if good:
            out.append(good)
    return out


def proponi(originale, meta, stile=None, pagine=()):
    """originale: percorso prima del riordino; meta: metadati; stile: Stile della Biblioteca;
    pagine: testo delle prime pagine. -> {"titolo", "autore", "volume", "fonte"}"""
    stile = stile or Stile()
    stem = re.split(r"[\\/]", originale or "")[-1]
    stem = re.sub(r"(\.(pdf|epub|mobi|azw3?))+$", "", stem, flags=re.I)
    name = pulisci(stem)
    testo = "\n".join(pagine[:6])
    testo_n = " " + norm(testo) + " "
    mt = next((meta.get(k) for k in ("Title", "title") if meta.get(k)), "")
    ma = next((meta.get(k) for k in ("Author", "author") if meta.get(k)), "")
    mt = mt if meta_buono(mt) else ""
    ma = ma if meta_buono(ma) else ""

    # 1) autore e titolo dal nome del file
    autore, titolo_nome = "", name
    pezzi = [p.strip() for p in re.split(r"\s+[-–—]\s+|\s+by\s+|\s+por\s+|(?<=\w)-(?=[A-ZÁÉÍÓÚ][a-záéíóú]+ [A-ZÁÉÍÓÚ])", name) if p.strip()]
    if len(pezzi) >= 2:
        noti = [i for i, p in enumerate(pezzi) if norm(p) in stile.autori]
        if noti:
            i = noti[0]
        elif ma and any(norm(ma).split()[-1:] == norm(p).split()[-1:] for p in pezzi):
            i = next(i for i, p in enumerate(pezzi) if norm(ma).split()[-1:] == norm(p).split()[-1:])
        else:
            cand = [(len(p), i) for i, p in enumerate(pezzi)
                    if 1 < len(p.split()) <= 4 and all(w[:1].isupper() or w.lower() in ("de", "y", "la", "del") for w in p.split())]
            i = min(cand)[1] if cand else len(pezzi) - 1
        autore = pezzi[i]
        titolo_nome = ", ".join(p for j, p in enumerate(pezzi) if j != i)
    if not autore and ma:
        autore = ma
    # autore all'inizio del nome senza trattino: "CHARLES AGYIN The Impact Of Prayer"
    if not autore:
        for a in sorted(stile.autori, key=len, reverse=True):
            if len(a) > 6 and norm(titolo_nome).startswith(a + " "):
                k = len(a.split())
                autore = " ".join(titolo_nome.split()[:k])
                titolo_nome = " ".join(titolo_nome.split()[k:])
                break

    # 2) candidati per il titolo, con un punteggio: quanto compaiono nel libro
    cands = []
    if titolo_nome:
        cands.append((titolo_nome, "nome"))
    if mt:
        cands.append((mt, "metadati"))
    for righe in righe_frontespizio(pagine):
        a_n = norm(autore)
        tl = [r for r in righe if norm(r) != a_n and presente(r, " " + a_n + " ") < 0.5]
        if tl:
            cands.append((" ".join(tl[:2]) if len(tl) > 1 and len(tl[0]) < 30 else tl[0], "frontespizio"))
    best, fonte, score = titolo_nome, "nome", -1
    for c, src in cands:
        if src == "frontespizio":
            continue
        s = presente(c, testo_n) + {"nome": 0.15, "metadati": 0.1}[src]
        if s > score:
            best, fonte, score = c, src, s
    # la pagina del titolo solo se nome e metadati sono spazzatura (nessuna parola nel libro, nomi come
    # "downloadfile-19", "Material-Escuela-Dominical--175-"): le righe di quelle pagine sono spesso dediche o indirizzi
    if score < 0.2 or len(norm(best).split()) < 2:
        for c, src in cands:
            if src == "frontespizio" and len(c.split()) <= 10 and c[:1].isupper() and not re.search(r"\d{3,}|\.\s", c):
                best, fonte = c, src
                break
    titolo = re.sub(r"\s*[:;]\s*", ", ", best.strip())
    titolo = re.sub(r"\s*\((?:spanish|english|portuguese) edition\)\s*$", "", titolo, flags=re.I).strip(" ,.")
    titolo = accenti_dal_testo(titolo, testo)
    titolo = stile.maiuscole_come_biblioteca(titolo)
    autore = re.sub(r"\s*[;&]\s*", " y ", autore).strip(" ,.")
    if autore.isupper() or autore.islower():
        autore = " ".join(w.capitalize() if len(w) > 2 or "." not in w else w.upper() for w in autore.lower().split())
    autore = accenti_dal_testo(autore, testo)
    return {"titolo": titolo, "autore": autore, "volume": volume(stem, mt), "fonte": fonte}
