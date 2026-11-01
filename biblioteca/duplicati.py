"""Duplicati, in sola lettura.
- Identici (stesso SHA-256) tra le sorgenti: si tiene una copia, le altre vanno in _duplicati.
- Gia' in Biblioteca: stesso hash di un libro della Biblioteca (sicuro), oppure stesso ISBN con
  titolo simile almeno al 60% (molto probabile).
- Probabili doppioni: titolo molto simile o stesso ISBN con titolo simile. Solo segnalati: decide l'utente.
  Un ISBN uguale da solo non basta: ci sono ISBN generici dell'editore e traduzioni.
"""
import difflib
import os
import re
import unicodedata
from collections import defaultdict

from .testo import split_name, to13

JUNK = re.compile(r"pdfdrive|spanish edition|\.pdf\.pdf|\(\d+\)|_\d+$|\bcopia\b|\bcopy\b|z-lib|libgen|\[|\]", re.I)
SIMILE_ISBN = 0.6
SIMILE_TITOLO = 0.72


def chiave(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\((spanish edition|z-library|otra copia[^)]*)\)", " ", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def somiglianza(a, b):
    a, b = chiave(a)[:80], chiave(b)[:80]
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def punteggio_nome(fn):
    stem = os.path.splitext(fn)[0]
    s = 0 if JUNK.search(fn) else 10
    s += 3 if " - " in stem else 0
    s -= sum(stem.count(c) for c in "_%+~")
    s -= 5 if re.search(r"Ã.|Â|â€", stem) else 0
    return s


def da_tenere(s):
    """Quale copia tenere tra identiche: con testo > con estensione > in una cartella tematica > nome piu' pulito
    > la prima trovata."""
    return ({"ok": 2, "poco": 1}.get(s.get("testo"), 0), 1 if s.get("estensione") else 0,
            1 if s.get("cartella") else 0, punteggio_nome(s["file"]), -s["n"])


def titolo_scheda(s):
    t = (s.get("meta") or {}).get("Title") or (s.get("meta") or {}).get("title") or ""
    return [x for x in (os.path.splitext(s["file"])[0], t) if x]


def identici(schede):
    """{sha: [schede]} solo per i gruppi con piu' copie; la prima di ogni gruppo e' quella da tenere."""
    g = defaultdict(list)
    for s in schede:
        if s.get("sha256"):
            g[s["sha256"]].append(s)
    return {h: sorted(v, key=da_tenere, reverse=True) for h, v in g.items() if len(v) > 1}


def indice_biblioteca(cache_bib):
    """Dal catalogo della Biblioteca: hash, ISBN e titoli (dal nome del file)."""
    per_sha, per_isbn, titoli = {}, defaultdict(list), []
    for rel, v in cache_bib.items():
        if v.get("sha256"):
            per_sha[v["sha256"]] = rel
        _, _, t, a = split_name(rel)
        for i in v.get("isbn") or []:
            per_isbn[to13(i)].append((rel, t))
        titoli.append((chiave(t), rel))
    return {"sha": per_sha, "isbn": per_isbn, "titoli": titoli}


def in_biblioteca(s, idx):
    """-> (decisione, motivo, libri simili). decisione: "identico", "isbn" o ""."""
    if s.get("sha256") in idx["sha"]:
        return "identico", "stesso file (SHA-256)", [idx["sha"][s["sha256"]]]
    nomi = titolo_scheda(s)
    for i in s.get("isbn") or []:
        for rel, t in idx["isbn"].get(to13(i), []):
            # i volumi di una collana hanno spesso lo stesso ISBN (Compendio Portavoz "1 Timoteo" e "Jonás"):
            # per i libri in collezione serve un titolo quasi identico
            soglia = 0.9 if split_name(rel)[1] else SIMILE_ISBN
            if max(somiglianza(n, t) for n in nomi) >= soglia:
                return "isbn", f"stesso ISBN {to13(i)} e titolo simile", [rel]
    simili = []
    cands = [chiave(n) for n in nomi]
    for kt, rel in idx["titoli"]:
        if not kt:
            continue
        best = max(difflib.SequenceMatcher(None, c[:80], kt[:80]).ratio() for c in cands)
        if best >= SIMILE_TITOLO or (len(kt) > 12 and any(kt in c for c in cands)):
            simili.append((round(best, 2), rel))
    return "", "", [rel for _, rel in sorted(simili, reverse=True)[:5]]


def probabili_tra_sorgenti(schede):
    """Coppie di libri diversi (hash diverso) che sembrano lo stesso libro: [(n1, n2, motivo)]."""
    libri = [s for s in schede if s.get("sha256")]
    uno_per_hash = {}
    for s in libri:
        uno_per_hash.setdefault(s["sha256"], s)
    libri = list(uno_per_hash.values())
    coppie, viste = [], set()
    per_isbn = defaultdict(list)
    for s in libri:
        for i in s.get("isbn") or []:
            per_isbn[to13(i)].append(s)
    for i, ss in per_isbn.items():
        for a in range(len(ss)):
            for b in range(a + 1, len(ss)):
                x, y = ss[a], ss[b]
                if max(somiglianza(p, q) for p in titolo_scheda(x) for q in titolo_scheda(y)) >= SIMILE_ISBN:
                    k = tuple(sorted((x["n"], y["n"])))
                    if k not in viste:
                        viste.add(k)
                        coppie.append((k[0], k[1], f"stesso ISBN {i} e titolo simile"))
    per_titolo = defaultdict(list)
    for s in libri:
        t = chiave((s.get("meta") or {}).get("Title") or (s.get("meta") or {}).get("title") or "")
        if len(t) > 8:
            per_titolo[t].append(s)
    for t, ss in per_titolo.items():
        for a in range(len(ss)):
            for b in range(a + 1, len(ss)):
                k = tuple(sorted((ss[a]["n"], ss[b]["n"])))
                if k not in viste:
                    viste.add(k)
                    coppie.append((k[0], k[1], "stesso titolo nei metadati"))
    return coppie
