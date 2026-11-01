"""Impostazioni salvate del programma (cartelle, categorie, esclusioni, AI, lingua).
Un file JSON in %APPDATA%\\Biblioteca: si scrive su un file temporaneo e poi si sostituisce,
cosi' un'interruzione non lascia mai un file a meta'.
Le chiavi delle AI non stanno qui in chiaro: vedi chiavi.py (cifratura di Windows).
"""
import copy
import json
import os

# categoria (nome della cartella) -> prefisso nel nome del file e descrizione.
# Sono le 30 categorie della Biblioteca originale; l'utente puo' cambiarle.
CATEGORIE = {
    "Apologética": ("Apologética", "Difesa della fede, cosmovisione"),
    "Apócrifos": ("Apócrifo", "Apocrifi, pseudepigrafi, letteratura intertestamentaria"),
    "Biblias": ("Biblia", "Versioni complete della Bibbia e Bibbie di studio"),
    "Biografías": ("Biografía", "Biografie e autobiografie cristiane"),
    "Bosquejos": ("Bosquejo", "Schemi di predicazione"),
    "Clásicos y Obras Completas": ("Clásico", "Padri, riformatori, opere complete di un autore"),
    "Comentarios": ("Comentario", "Commentari biblici, singoli e in collana"),
    "Consejería y Adicciones": ("Consejería", "Consulenza biblica, dipendenze"),
    "Devocionales": ("Devocional", "Letture quotidiane e meditazioni"),
    "Diccionarios": ("Diccionario", "Dizionari, enciclopedie, concordanze"),
    "Espíritu Santo y Dones": ("Espíritu Santo", "Pneumatologia pratica, doni, profezia, guarigione"),
    "Estudios Bíblicos": ("Estudio", "Studi su libri e personaggi biblici, introduzioni alla Bibbia"),
    "Evangelismo y Misiones": ("Evangelismo", "Evangelizzazione, missioni, fondazione di chiese"),
    "Familia y Matrimonio": ("Familia", "Matrimonio, figli, sessualità"),
    "Hermenéutica": ("Hermenéutica", "Interpretazione della Bibbia"),
    "Historia Bíblica y Arqueología": ("Historia Bíblica", "Storia di Israele e del mondo biblico, archeologia, atlanti"),
    "Historia de la Iglesia": ("Historia Iglesia", "Storia del cristianesimo, Riforma, risvegli"),
    "Homilética": ("Homilética", "Come predicare e insegnare"),
    "Interlineales": ("Interlineal", "Interlineari, testi originali, grammatiche di greco ed ebraico"),
    "Ministerio e Iglesia": ("Ministerio", "Ministero pastorale, leadership, vita di chiesa"),
    "Música y Alabanza": ("Música", "Canzonieri, spartiti, ministero di lode"),
    "Niños y Jóvenes": ("Niños", "Scuola domenicale, materiale per bambini e adolescenti"),
    "No Cristiano": ("No Cristiano", "Libri laici o di altre religioni (separati dal resto)"),
    "Novela Cristiana": ("Novela", "Romanzi e narrativa cristiana"),
    "Oración y Guerra Espiritual": ("Oración", "Preghiera, digiuno, guerra spirituale, liberazione"),
    "Revistas": ("Revista", "Riviste e periodici"),
    "Sectas y Falsas Doctrinas": ("Sectas", "Sette, eresie, religioni comparate da prospettiva cristiana"),
    "Sermones": ("Sermón", "Raccolte di prediche"),
    "Teología": ("Teología", "Teologia sistematica e dottrina"),
    "Vida Cristiana": ("Vida Cristiana", "Crescita spirituale, vita pratica del credente"),
}

PREDEFINITE = {
    "lingua": "",                 # "" = quella di Windows
    "biblioteca": "",             # cartella della Biblioteca ordinata (destinazione)
    "sorgenti": [],               # cartelle da ordinare, o la cartella dei libri nuovi
    "protette": [],               # cartelle che il programma non legge, non scrive e non sposta
    "duplicati": "",              # dove vanno le copie identiche ("" = <biblioteca>\..\_duplicati)
    "altri_file": "",             # dove vanno i file che non sono libri
    "categorie": {k: {"prefisso": p, "descrizione": d} for k, (p, d) in CATEGORIE.items()},
    "esclusioni": ["Esoterismo", "Commentario mormone", "EPUB di sole immagini"],
    "soglia_sicura": 0.7,         # categoria accettata da sola sopra questa sicurezza (98,7% giuste nella prova)
    "ai": {"servizio": "nessuno", "modello": "", "modello_locale": "auto", "cartella_modelli": ""},
}


def cartella_app():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "Biblioteca")
    os.makedirs(d, exist_ok=True)
    return d


def percorso():
    return os.path.join(cartella_app(), "impostazioni.json")


def carica(path=None):
    path = path or percorso()
    imp = copy.deepcopy(PREDEFINITE)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                salvate = json.load(f)
        except (OSError, json.JSONDecodeError):
            salvate = {}
        for k, v in salvate.items():
            if k == "ai" and isinstance(v, dict):
                imp["ai"].update(v)
            elif k in imp:
                imp[k] = v
    return imp


def salva(imp, path=None):
    path = path or percorso()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(imp, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def cartelle(imp):
    """Le cartelle di lavoro ricavate dalle impostazioni (percorsi assoluti)."""
    bib = os.path.abspath(imp["biblioteca"]) if imp["biblioteca"] else ""
    padre = os.path.dirname(bib) if bib else ""
    return {
        "biblioteca": bib,
        "sorgenti": [os.path.abspath(s) for s in imp["sorgenti"] if s],
        "protette": [os.path.abspath(s) for s in imp["protette"] if s],
        "duplicati": os.path.abspath(imp["duplicati"]) if imp["duplicati"] else os.path.join(padre, "_duplicati"),
        "altri_file": os.path.abspath(imp["altri_file"]) if imp["altri_file"] else os.path.join(padre, "_altri_file"),
        # dati del programma dentro la Biblioteca (cartella con "_": il catalogo la salta),
        # cosi' i log per annullare viaggiano insieme ai libri nei backup
        "dati": os.path.join(bib, "_programma") if bib else os.path.join(cartella_app(), "dati"),
    }


def prefisso(imp, categoria):
    c = imp["categorie"].get(categoria)
    return c["prefisso"] if c else categoria
