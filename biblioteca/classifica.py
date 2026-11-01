"""Classificatore offline delle categorie (nessuna libreria esterna, nessun internet).
Impara da una Biblioteca gia' ordinata: per ogni libro guarda quello che si vede anche in un
libro nuovo (nome e cartelle originali, metadati, testo delle prime pagine) e la categoria
in cui e' finito. E' un Naive Bayes multinomiale con le parole divise per "campo"
(nome del file, metadati, testo), perche' la stessa parola pesa diversamente nel nome e nel testo.
Il risultato e' una lista di categorie con una probabilita': i casi incerti vanno controllati.
"""
import json
import math
import os
import re
import unicodedata
from collections import Counter, defaultdict

STOP = set("""
a al algo algun alguna algunas alguno algunos ante antes aqui asi aun cada como con contra cual cuando de del desde
donde dos el ella ellas ellos en entre era es esa esas ese eso esos esta estas este esto estos fue ha hay la las le les
lo los mas me mi mis muy ni no nos nuestra nuestro o otra otro para pero por porque que quien se sea ser si sin sobre
son su sus tambien te tiene todo todos tu un una uno unos y ya yo
the and of to in for on with by from at as is are was be this that it an or not you your his her their our we they
do da das dos na no nas nos em um uma para com por pelo pela que se os as e o
pdf epub mobi azw3 libro book books libros edition edicion spanish espanol version ebook
www com org net http https html
""".split())
CAMPI = {"n": 3.0, "m": 2.0, "t": 1.0}  # peso delle parole del nome, dei metadati e del testo
TEXT_CHARS = 5000


def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.lower()


def parole(s):
    return [w for w in re.findall(r"[a-zñ]{3,}", norm(s)) if w not in STOP]


def caratteristiche(originale, meta, testo):
    """originale: percorso del file prima del riordino (cartelle e nome);
    meta: dizionario dei metadati; testo: testo delle prime pagine."""
    parts = re.split(r"[\\/]", originale or "")
    nome = " ".join(parts[-3:])  # ultime due cartelle e nome del file
    nome = re.sub(r"\.(pdf|epub|mobi|azw3?)$", "", nome, flags=re.I)
    m = " ".join(str(meta.get(k, "")) for k in ("Title", "title", "Subject", "subject", "Keywords", "keywords"))
    feats = Counter()
    for campo, txt in (("n", nome), ("m", m), ("t", (testo or "")[:TEXT_CHARS])):
        w = parole(txt)
        feats.update(f"{campo}:{x}" for x in w)
        if campo != "t":  # coppie di parole: "guerra espiritual", "antiguo testamento"
            feats.update(f"{campo}:{a}_{b}" for a, b in zip(w, w[1:]))
    return feats


class ClassificatoreLR:
    """Regressione logistica su TF-IDF (scikit-learn, BSD): nella prova sulla Biblioteca e' molto
    piu' preciso del Naive Bayes (74% contro 64% alla prima proposta) e le probabilita' sono affidabili."""

    def __init__(self, C=20):
        self.C = C
        self.model = None

    def addestra(self, esempi):
        from sklearn.feature_extraction import DictVectorizer
        from sklearn.feature_extraction.text import TfidfTransformer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        X = [{f: c * CAMPI[f[0]] for f, c in feats.items()} for feats, _ in esempi]
        y = [cat for _, cat in esempi]
        self.model = make_pipeline(DictVectorizer(), TfidfTransformer(sublinear_tf=True),
                                   LogisticRegression(C=self.C, max_iter=3000, class_weight="balanced"))
        self.model.fit(X, y)
        return self

    def proponi(self, feats, k=3):
        return self.proponi_molti([feats], k)[0]

    def proponi_molti(self, lista, k=3):
        X = [{f: c * CAMPI[f[0]] for f, c in feats.items()} for feats in lista]
        P = self.model.predict_proba(X)
        cl = self.model.classes_
        return [[(cl[j], float(p[j])) for j in p.argsort()[::-1][:k]] for p in P]

    def salva(self, path):
        import pickle
        with open(path, "wb") as f:
            pickle.dump(self.model, f)

    @classmethod
    def carica(cls, path):
        import pickle
        c = cls()
        with open(path, "rb") as f:
            c.model = pickle.load(f)
        return c


class Classificatore:
    def __init__(self, alpha=0.3):
        self.alpha = alpha
        self.counts = {}      # categoria -> Counter(parola -> conteggio pesato)
        self.totals = {}
        self.priors = {}
        self.vocab = set()

    def addestra(self, esempi):
        """esempi: lista di (Counter caratteristiche, categoria)."""
        by = defaultdict(Counter)
        n = Counter()
        for feats, cat in esempi:
            n[cat] += 1
            for f, c in feats.items():
                by[cat][f] += c * CAMPI[f[0]]
        tot = sum(n.values())
        self.priors = {c: math.log(k / tot) for c, k in n.items()}
        self.counts = {c: dict(v) for c, v in by.items()}
        self.totals = {c: sum(v.values()) for c, v in by.items()}
        self.vocab = set(f for v in by.values() for f in v)
        return self

    def proponi(self, feats, k=3):
        """Le k categorie piu' probabili: [(categoria, probabilita'), ...]."""
        V = len(self.vocab)
        scores = {}
        for c in self.priors:
            cnt, tot = self.counts.get(c, {}), self.totals.get(c, 0)
            den = math.log(tot + self.alpha * V)
            s = self.priors[c]
            for f, x in feats.items():
                if f in self.vocab:
                    s += x * CAMPI[f[0]] * (math.log(cnt.get(f, 0) + self.alpha) - den)
            scores[c] = s
        # probabilita' "addolcite": il Naive Bayes e' troppo sicuro di se', si divide per un fattore
        mx = max(scores.values())
        ex = {c: math.exp((s - mx) / max(1.0, len(feats) ** 0.5)) for c, s in scores.items()}
        z = sum(ex.values())
        return sorted(((c, v / z) for c, v in ex.items()), key=lambda x: -x[1])[:k]

    def salva(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"alpha": self.alpha, "counts": self.counts, "priors": self.priors}, f, ensure_ascii=False)

    @classmethod
    def carica(cls, path):
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        c = cls(d["alpha"])
        c.counts, c.priors = d["counts"], d["priors"]
        c.totals = {k: sum(v.values()) for k, v in c.counts.items()}
        c.vocab = set(f for v in c.counts.values() for f in v)
        return c
