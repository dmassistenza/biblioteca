"""Intelligenza artificiale facoltativa per titolo, sottotitolo e autore.
Si usa solo dove le proposte del programma (nomi.py) sono incerte.
Tutti i servizi gratuiti previsti parlano lo stesso protocollo, quello "compatibile OpenAI"
(POST .../chat/completions), quindi un solo client li serve tutti:
- AI sul PC: llama.cpp (llama-server, licenza MIT) con un modello aperto, su http://127.0.0.1;
- cloud gratuiti: Google Gemini, Groq, Mistral (account gratuito, senza carta).
Solo libreria standard di Python: nessuna dipendenza in piu' da distribuire.
"""
import json
import re
import time
import urllib.error
import urllib.request

SERVIZI = {
    "locale": {"url": "http://127.0.0.1:8088/v1", "modello": "locale", "pausa": 0.0},
    # provato il 31/10/2026: ~1 s a libro, nessun limite raggiunto con 6,5 s di pausa (i Gemini piu' grandi,
    # gratis, facevano aspettare minuti). "latest" segue da solo le nuove versioni.
    "gemini": {"url": "https://generativelanguage.googleapis.com/v1beta/openai", "modello": "gemini-flash-lite-latest", "pausa": 6.5},
    "groq": {"url": "https://api.groq.com/openai/v1", "modello": "llama-3.3-70b-versatile", "pausa": 2.5},
    "mistral": {"url": "https://api.mistral.ai/v1", "modello": "mistral-small-latest", "pausa": 1.5},
}

ISTRUZIONI = """Sei un bibliotecario. Ricevi il nome del file, i metadati e le prime pagine di un libro \
(spesso cristiano evangelico, quasi sempre in spagnolo). Rispondi SOLO con un oggetto JSON:
{"titolo": "...", "sottotitolo": "...", "autore": "...", "lingua": "es|en|pt|it|..."}
Regole:
- Il titolo e' quello stampato sul frontespizio o sulla copertina, nella lingua del libro, NON la traduzione \
del nome del file (un file "Ultimate Security" che contiene "Seguridad suprema" ha titolo "Seguridad suprema").
- Nei libri tradotti la pagina del copyright riporta anche il titolo originale ("Originally published as...", \
"Título original", "Copyright ... by"): NON usarlo. Usa il titolo nella lingua in cui e' scritto il libro.
- Maiuscole come in spagnolo: solo la prima parola e i nomi propri ("Dios", "Jesús", "Biblia", "Espíritu Santo").
- Il sottotitolo va a parte, senza il titolo; vuoto se non c'e'. Niente nome della collana o della casa editrice.
- Autore: "Nome Cognome"; piu' autori separati da ", " e l'ultimo da " y "; per i curatori aggiungi " (eds.)". \
Se il libro non ha un autore persona, metti l'editore o il ministero che lo firma \
(per esempio "Ediciones Las Américas"). Vuoto solo se non si capisce. Non inventare nulla."""

MAX_TESTO = 4000  # caratteri delle prime pagine: bastano per frontespizio e copyright, e restano pochi token


class ErroreAI(Exception):
    """tipo: 'chiave' (chiave sbagliata), 'limite' (limite gratuito raggiunto), 'rete', 'risposta'."""

    def __init__(self, tipo, msg, attesa=0):
        super().__init__(msg)
        self.tipo, self.attesa = tipo, attesa


PREFISSI_CHIAVE = ("AIza", "AQ.", "gsk_", "sk-")


def estrai_chiave(testo):
    """La chiave dentro quello che l'utente ha incollato: spesso copia anche "Nome:", "Progetto:"...
    Prende la parola con un prefisso noto, altrimenti la parola piu' lunga che sembra una chiave."""
    parole = re.findall(r"[0-9A-Za-z_\-.]{20,}", testo or "")
    noti = [w for w in parole if w.startswith(PREFISSI_CHIAVE)]
    if noti:
        return noti[-1]
    parole = [w for w in parole if not w.startswith("projects")]
    return max(parole, key=len) if parole else ""


def messaggio_libro(originale, meta, pagine):
    m = {k: str(v)[:200] for k, v in (meta or {}).items() if k.lower() in ("title", "author", "subject", "creator", "publisher")}
    testo = ""
    for p in pagine or ():
        p = re.sub(r"[ \t]+", " ", p).strip()
        if p:
            testo += p + "\n---\n"
        if len(testo) >= MAX_TESTO:
            break
    nome = re.split(r"[\\/]", originale or "")[-1]
    return f"Nome del file: {nome}\nMetadati: {json.dumps(m, ensure_ascii=False)}\nPrime pagine:\n{testo[:MAX_TESTO]}"


class Client:
    def __init__(self, url, modello, chiave="", timeout=180, extra=None):
        self.url, self.modello, self.chiave, self.timeout = url.rstrip("/"), modello, chiave, timeout
        self.extra = extra or {}

    def _post(self, path, corpo):
        req = urllib.request.Request(self.url + path, data=json.dumps(corpo).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json"})
        if self.chiave:
            req.add_header("Authorization", "Bearer " + self.chiave)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            testo = e.read().decode("utf-8", "replace")[:300]
            if e.code in (401, 403):
                raise ErroreAI("chiave", f"{e.code}: {testo}") from None
            if e.code == 429:
                attesa = int(e.headers.get("retry-after", "0") or 0) or 60
                raise ErroreAI("limite", f"429: {testo}", attesa) from None
            if e.code >= 500:
                raise ErroreAI("rete", f"{e.code}: {testo}", 20) from None
            raise ErroreAI("risposta", f"{e.code}: {testo}") from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            raise ErroreAI("rete", str(e), 20) from None

    def chiedi(self, testo_utente, max_tokens=300):
        corpo = {"model": self.modello, "max_tokens": max_tokens, "temperature": 0,
                 "response_format": {"type": "json_object"},
                 "messages": [{"role": "system", "content": ISTRUZIONI}, {"role": "user", "content": testo_utente}]}
        corpo.update(self.extra)
        r = self._post("/chat/completions", corpo)
        try:
            out = r["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise ErroreAI("risposta", json.dumps(r)[:300]) from None
        return leggi_json(out), r.get("usage", {})

    def proponi(self, originale, meta, pagine, tentativi=4):
        """Titolo, sottotitolo e autore per un libro; aspetta e riprova sui limiti e sugli errori di rete."""
        for n in range(tentativi):
            try:
                return self.chiedi(messaggio_libro(originale, meta, pagine))
            except ErroreAI as e:
                if e.tipo in ("limite", "rete") and n + 1 < tentativi:
                    time.sleep(e.attesa)
                    continue
                raise


SCHEMA = {"type": "object", "additionalProperties": False, "required": ["titolo", "sottotitolo", "autore", "lingua"],
          "properties": {k: {"type": "string"} for k in ("titolo", "sottotitolo", "autore", "lingua")}}

# Claude a pagamento: prezzi per milione di token (input, output) per la stima del costo
MODELLI_CLAUDE = {"claude-opus-5-5": (4.00, 20.00), "claude-haiku-5-5": (0.10, 0.50)}


class ClientClaude:
    """Claude con la chiave dell'utente (SDK ufficiale anthropic). Uscita JSON garantita dallo schema."""

    def __init__(self, chiave, modello="claude-opus-5-5", timeout=120):
        import anthropic
        self.anthropic = anthropic
        self.modello = modello
        self.client = anthropic.Anthropic(api_key=chiave, timeout=timeout, max_retries=2)

    def chiedi(self, testo_utente, max_tokens=1024):
        a = self.anthropic
        kw = dict(model=self.modello, max_tokens=max_tokens, system=ISTRUZIONI,
                  messages=[{"role": "user", "content": testo_utente}],
                  output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}})
        try:
            if self.modello == "claude-opus-5-5":  # se un filtro rifiuta, il server riprova da solo con un altro modello
                r = self.client.beta.messages.create(**kw, betas=["server-side-fallback-2026-07-01"], fallbacks="default")
            else:
                r = self.client.messages.create(**kw)
        except a.AuthenticationError as e:
            raise ErroreAI("chiave", str(e)[:300]) from None
        except a.PermissionDeniedError as e:
            raise ErroreAI("chiave", str(e)[:300]) from None
        except a.RateLimitError as e:
            raise ErroreAI("limite", str(e)[:300], int(e.response.headers.get("retry-after", "60") or 60)) from None
        except a.APIStatusError as e:
            if e.status_code >= 500:
                raise ErroreAI("rete", str(e)[:300], 20) from None
            if e.status_code == 402 or "credit" in str(e).lower():
                raise ErroreAI("credito", str(e)[:300]) from None
            raise ErroreAI("risposta", str(e)[:300]) from None
        except a.APIConnectionError as e:
            raise ErroreAI("rete", str(e)[:300], 20) from None
        if r.stop_reason == "refusal":
            raise ErroreAI("risposta", "richiesta rifiutata dal filtro di sicurezza")
        testo = "".join(b.text for b in r.content if b.type == "text")
        uso = {"prompt_tokens": r.usage.input_tokens, "completion_tokens": r.usage.output_tokens}
        return leggi_json(testo), uso

    def proponi(self, originale, meta, pagine, tentativi=4):
        return Client.proponi(self, originale, meta, pagine, tentativi)


def stima_costo(proposte_testi, modello):
    """Costo stimato in dollari: circa 3,5 caratteri per token, piu' le istruzioni; ~80 token di risposta."""
    pin, pout = MODELLI_CLAUDE[modello]
    tok_in = sum(len(t) / 3.5 + len(ISTRUZIONI) / 3.5 for t in proposte_testi)
    tok_out = 80 * len(proposte_testi)
    return round(tok_in / 1e6 * pin + tok_out / 1e6 * pout, 2)


def crea_client(servizio, chiave="", modello=""):
    if servizio == "claude":
        return ClientClaude(chiave, modello or "claude-opus-5-5")
    cfg = SERVIZI[servizio]
    extra = {"chat_template_kwargs": {"enable_thinking": False}} if servizio == "locale" else {}
    return Client(cfg["url"], modello or cfg["modello"], chiave, extra=extra)


def prova(client):
    """Una domanda piccola per controllare chiave e collegamento. -> (ok, messaggio)."""
    try:
        r, _ = client.chiedi(messaggio_libro("Prova - Libro.pdf", {"Title": "El amor de Dios"},
                                             ["EL AMOR DE DIOS\nJuan Pérez\nEditorial Prueba"]), max_tokens=200)
        return True, f"OK: {r.get('titolo')} / {r.get('autore')}"
    except ErroreAI as e:
        return False, f"{e.tipo}: {e}"


def rifinisci(p, stile=None):
    """Mette la risposta dell'AI nella forma dei nomi della Biblioteca:
    sottotitolo separato, niente punto finale, maiuscole come nella Biblioteca."""
    p = dict(p)
    tit, sub = p["titolo"].strip(), p["sottotitolo"].strip()
    if not sub and ":" in tit:
        tit, sub = (x.strip() for x in tit.split(":", 1))
    tit, sub = tit.rstrip(" ."), sub.rstrip(" .")
    if stile:
        for nome, t in (("titolo", tit), ("sottotitolo", sub)):
            ws = [w for w in re.findall(r"[^\W\d_]+", t) if len(w) > 3]
            # solo se l'AI ha scritto TUTTO MAIUSCOLO o Ogni Parola Maiuscola: altrimenti si fida delle sue maiuscole
            if ws and (t.isupper() or sum(w[:1].isupper() for w in ws) / len(ws) > 0.6):
                t = stile.maiuscole_come_biblioteca(t)
            if nome == "titolo":
                tit = t
            else:
                sub = t
    aut = p["autore"].strip()
    from .nomi import meta_buono
    if aut and not meta_buono(aut):  # l'AI a volte copia l'autore spazzatura dei metadati ("Windows User")
        aut = ""
    if aut.isupper():
        aut = " ".join(w.capitalize() if len(w) > 2 or "." not in w else w for w in aut.lower().split())
    p.update(titolo=tit, sottotitolo=sub, autore=aut)
    return p


def leggi_json(s):
    s = re.sub(r"<think>.*?</think>", "", s, flags=re.S).strip()
    m = re.search(r"\{.*\}", s, re.S)
    if not m:
        raise ErroreAI("risposta", "nessun JSON: " + s[:200])
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        raise ErroreAI("risposta", "JSON non valido: " + s[:200]) from None
    return {k: str(d.get(k) or "").strip() for k in ("titolo", "sottotitolo", "autore", "lingua")}
