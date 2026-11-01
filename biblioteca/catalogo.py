"""Catalogo web della Biblioteca (Catalogo.html): un solo file HTML, senza internet, dati incorporati.
I dati vengono dalla cache dell'analisi della Biblioteca (inventario.analizza_biblioteca):
pagine, ISBN, prologo, edizione. Titolo, autore, categoria e collezione vengono dal nome del file.
I temi si assegnano con espressioni regolari sul titolo, sulla collezione e sul prologo.
"""
import json
import os
import re
import unicodedata
from collections import Counter

from .testo import split_name

MODELLO = os.path.join(os.path.dirname(__file__), "risorse", "catalogo_modello.html")

# tema -> espressioni (spagnolo, inglese, portoghese). Un tema si assegna se compare nel
# titolo o nella collezione, oppure almeno 3 volte nel prologo.
TEMI = {
    "Preghiera": r"oraci[oó]n|\borar\b|intercesi|intercesor|prayer|\bpray|ora[cç][aã]o",
    "Digiuno": r"ayuno|ayunar|fasting|jejum",
    "Guerra spirituale e liberazione": r"guerra espiritual|liberaci[oó]n|demonio|endemoniad|esp[ií]ritus? inmundo|fortalezas|maldici[oó]n|"
                                       r"spiritual warfare|deliverance|liberta[cç][aã]o|batalla espiritual",
    "Spirito Santo": r"esp[ií]ritu santo|holy spirit|esp[ií]rito santo|pentecost|bautismo en el esp|unci[oó]n",
    "Doni, profezia e sogni": r"\bdones\b|profec[ií]a|prof[eé]tic|\bprofeta|prophe|sue[ñn]os|visiones|dreams|revelaci[oó]n prof",
    "Guarigione e miracoli": r"sanidad|sanar\b|milagro|healing|miracle|cura divina|sanidad divina|se[ñn]ales y prodigios",
    "Fede": r"\bfe\b|faith|\bcreer\b|confianza en dios",
    "Grazia e salvezza": r"gracia|salvaci[oó]n|justificaci|redenci|nuevo nacimiento|grace|salvation|evangelio de",
    "Santità e consacrazione": r"santidad|holiness|santifica|consagraci|pureza",
    "Perdono e riconciliazione": r"perd[oó]n|perdonar|forgive|reconcilia",
    "Amore di Dio": r"amor de dios|el amor\b|love of god|amar a dios",
    "Matrimonio": r"matrimonio|marriage|casamiento|c[oó]nyuge|noviazgo|\bcasados?\b|esposos",
    "Famiglia e figli": r"familia|\bhijos\b|crianza|parenting|family|maternidad|paternidad|\bpadres\b",
    "Sessualità": r"sexual|sexo\b|pornograf|sexualidad",
    "Donne": r"\bmujer(es)?\b|women|femenin|\besposa\b|\bmadres?\b",
    "Giovani": r"j[oó]venes|juventud|adolescen|youth|\bteen",
    "Bambini": r"ni[ñn]os|infantil|escuela dominical|\bkids\b|children|para ni",
    "Leadership": r"liderazgo|\bl[ií]der|leadership",
    "Chiesa e ministero pastorale": r"iglesia local|pastor(es|al|ado)?\b|ministerio|church|congregaci",
    "Predicazione": r"predicaci[oó]n|predicar|serm[oó]n|sermones|homil|preaching|bosquejo",
    "Evangelizzazione e missioni": r"evangeli[sz]|misi[oó]n(es)?\b|misioner|mission|gran comisi|plantaci[oó]n de iglesias|ganar almas",
    "Profezia biblica e fine dei tempi": r"escatolog|apocalipsis|fin de los tiempos|[uú]ltimos tiempos|rapto|arrebatamiento|anticristo|milenio|"
                                         r"segunda venida|end times|tribulaci[oó]n|\bdaniel\b|revelation",
    "Lode e adorazione": r"alabanza|adoraci[oó]n|worship|adorar|alabar|c[aá]ntico|himno",
    "Sofferenza e dolore": r"sufrimiento|\bdolor|duelo|aflicci|pruebas|suffering|grief|\bp[eé]rdida",
    "Ansia, depressione ed emozioni": r"ansiedad|depresi[oó]n|miedo|temor\b|preocupaci|emociones|anxiety|depression|soledad|\bira\b",
    "Denaro e prosperità": r"dinero|finanzas|prosperidad|riqueza|diezmo|ofrenda|money|mayordom|econom",
    "Regno di Dio": r"reino de dios|reino de los cielos|kingdom|reino de",
    "Gesù Cristo": r"jesucristo|cristolog|\bla cruz\b|resurrecci|vida de jes[uú]s|jesus christ|el mes[ií]as",
    "Bibbia e interpretazione": r"hermen[eé]utica|interpretaci[oó]n|ex[eé]gesis|inspiraci[oó]n|\bcanon\b|estudiar la biblia|bible study",
    "Apologetica, creazione e scienza": r"apolog|creaci[oó]n|evoluci|darwin|ciencia|dise[ñn]o inteligente|ate[ií]s|existencia de dios",
    "Storia": r"historia(?!s? de la biblia)|hist[oó]ric|arqueolog|reforma protestante|history|antigua",
    "Discepolato e crescita": r"discipulado|disc[ií]pulo|crecimiento espiritual|madurez|discipleship|vida cristiana",
    "Identità e autostima": r"identidad|autoestima|identity|qui[eé]n soy|valor propio",
    "Dipendenze": r"adicci|alcohol|drogas|addiction|\bvicio",
    "Israele e popolo ebraico": r"israel|jud[ií]o|hebreo|jewish|sinagoga|tabern[aá]culo|jerusal[eé]n",
    "Angeli, cielo e inferno": r"[aá]ngel|mundo espiritual|infierno|\bcielo\b|heaven|\bhell\b|eternidad",
    "Sette e false dottrine": r"secta|herej|falsas? doctrinas?|testigos de jehov|mormon|catolicismo|nueva era|ocult|brujer",
    "Teologia e dottrina": r"teolog[ií]a|doctrina|trinidad|soteriolog|eclesiolog|pneumatolog|atributos de dios",
}
# nomi dei temi in inglese e spagnolo, per la pagina trilingue
TEMI_TR = {
    "Preghiera": ("Prayer", "Oración"),
    "Digiuno": ("Fasting", "Ayuno"),
    "Guerra spirituale e liberazione": ("Spiritual warfare and deliverance", "Guerra espiritual y liberación"),
    "Spirito Santo": ("Holy Spirit", "Espíritu Santo"),
    "Doni, profezia e sogni": ("Gifts, prophecy and dreams", "Dones, profecía y sueños"),
    "Guarigione e miracoli": ("Healing and miracles", "Sanidad y milagros"),
    "Fede": ("Faith", "Fe"),
    "Grazia e salvezza": ("Grace and salvation", "Gracia y salvación"),
    "Santità e consacrazione": ("Holiness and consecration", "Santidad y consagración"),
    "Perdono e riconciliazione": ("Forgiveness and reconciliation", "Perdón y reconciliación"),
    "Amore di Dio": ("Love of God", "Amor de Dios"),
    "Matrimonio": ("Marriage", "Matrimonio"),
    "Famiglia e figli": ("Family and children", "Familia e hijos"),
    "Sessualità": ("Sexuality", "Sexualidad"),
    "Donne": ("Women", "Mujeres"),
    "Giovani": ("Youth", "Jóvenes"),
    "Bambini": ("Children", "Niños"),
    "Leadership": ("Leadership", "Liderazgo"),
    "Chiesa e ministero pastorale": ("Church and pastoral ministry", "Iglesia y ministerio pastoral"),
    "Predicazione": ("Preaching", "Predicación"),
    "Evangelizzazione e missioni": ("Evangelism and missions", "Evangelismo y misiones"),
    "Profezia biblica e fine dei tempi": ("Bible prophecy and end times", "Profecía bíblica y fin de los tiempos"),
    "Lode e adorazione": ("Praise and worship", "Alabanza y adoración"),
    "Sofferenza e dolore": ("Suffering and grief", "Sufrimiento y dolor"),
    "Ansia, depressione ed emozioni": ("Anxiety, depression and emotions", "Ansiedad, depresión y emociones"),
    "Denaro e prosperità": ("Money and prosperity", "Dinero y prosperidad"),
    "Regno di Dio": ("Kingdom of God", "Reino de Dios"),
    "Gesù Cristo": ("Jesus Christ", "Jesucristo"),
    "Bibbia e interpretazione": ("Bible and interpretation", "Biblia e interpretación"),
    "Apologetica, creazione e scienza": ("Apologetics, creation and science", "Apologética, creación y ciencia"),
    "Storia": ("History", "Historia"),
    "Discepolato e crescita": ("Discipleship and growth", "Discipulado y crecimiento"),
    "Identità e autostima": ("Identity and self-esteem", "Identidad y autoestima"),
    "Dipendenze": ("Addictions", "Adicciones"),
    "Israele e popolo ebraico": ("Israel and the Jewish people", "Israel y el pueblo judío"),
    "Angeli, cielo e inferno": ("Angels, heaven and hell", "Ángeles, cielo e infierno"),
    "Sette e false dottrine": ("Cults and false doctrines", "Sectas y falsas doctrinas"),
    "Teologia e dottrina": ("Theology and doctrine", "Teología y doctrina"),
}
assert set(TEMI_TR) == set(TEMI), set(TEMI) ^ set(TEMI_TR)
TEMI_RE = {k: re.compile(v, re.I) for k, v in TEMI.items()}
# parole troppo comuni nei prologhi ("historia" = racconto, "iglesia", "cielo"...): questi temi
# si assegnano solo dal titolo o dalla collezione
SOLO_TITOLO = {"Storia", "Angeli, cielo e inferno", "Israele e popolo ebraico", "Fede", "Donne",
               "Chiesa e ministero pastorale", "Doni, profezia e sogni", "Famiglia e figli", "Bambini",
               "Teologia e dottrina", "Grazia e salvezza", "Bibbia e interpretazione", "Regno di Dio"}
MAX_TEMI = 6
SOGLIA_PROLOGO = 4

def temi(title, coll, prologue):
    head = f"{title} {coll}"
    scored = []
    for i, (name, rx) in enumerate(TEMI_RE.items()):
        s = 10 * len(rx.findall(head))
        if name not in SOLO_TITOLO:
            s += len(rx.findall(prologue))
        if s >= SOGLIA_PROLOGO:
            scored.append((s, i))
    return [i for _, i in sorted(scored, reverse=True)[:MAX_TEMI]]


def naturale(s):
    return [int(t) if t.isdigit() else unicodedata.normalize("NFKD", t.lower()) for t in re.split(r"(\d+)", s)]


def stato_testo(v):
    if v.get("stato") in ("errore", "protetto"):
        return v["stato"]
    return v.get("testo") or "ok"


def genera(biblioteca, cache, uscita=None):
    """Scrive <biblioteca>\\Catalogo.html. -> riepilogo con i conteggi."""
    uscita = uscita or os.path.join(biblioteca, "Catalogo.html")
    libri = []
    for rel, v in cache.items():
        if not os.path.isfile(os.path.join(biblioteca, rel)):
            continue  # libro spostato dopo l'analisi
        cat, coll, title, author = split_name(rel)
        pro = v.get("prologo") or ""
        libri.append({
            "c": cat, "k": coll, "t": title, "a": author,
            "p": rel.replace(os.sep, "/"), "n": v.get("pagine") or 0, "x": pro,
            "y": v.get("tipo_prologo") or "", "g": v.get("pagina_prologo"), "s": stato_testo(v),
            "h": temi(title, coll, pro), "i": v.get("isbn") or [],
        })
    libri.sort(key=lambda b: (naturale(b["c"]), naturale(b["k"]), naturale(b["t"])))
    data = {"temi": [{"it": k, "en": TEMI_TR[k][0], "es": TEMI_TR[k][1]} for k in TEMI], "libri": libri}
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    with open(MODELLO, encoding="utf-8") as f:
        html = f.read().replace("/*__DATI__*/null", payload)
    tmp = uscita + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(html)
    os.replace(tmp, uscita)
    cnt = Counter(t for b in libri for t in b["h"])
    return {"file": uscita, "libri": len(libri), "con_prologo": sum(1 for b in libri if b["x"]),
            "con_isbn": sum(1 for b in libri if b["i"]), "kb": os.path.getsize(uscita) // 1024,
            "temi": {list(TEMI)[i]: n for i, n in cnt.most_common()}, "senza_temi": sum(1 for b in libri if not b["h"])}
