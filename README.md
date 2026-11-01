# Biblioteca

**IT** · Programma gratuito per Windows che riordina una biblioteca di libri PDF ed EPUB: riconosce titolo, autore e ISBN, trova i doppioni, propone categorie e collezioni e crea un catalogo consultabile offline in italiano, inglese e spagnolo. L'AI è facoltativa e gratuita (sul PC o nel cloud).

**EN** · Free Windows program that organizes a library of PDF and EPUB books: it recognizes title, author and ISBN, finds duplicates, suggests categories and collections, and builds an offline catalog in Italian, English and Spanish. AI is optional and free (on the PC or in the cloud).

**ES** · Programa gratuito para Windows que ordena una biblioteca de libros PDF y EPUB: reconoce título, autor e ISBN, encuentra duplicados, propone categorías y colecciones y crea un catálogo consultable sin conexión en italiano, inglés y español. La IA es opcional y gratuita (en el PC o en la nube).

---

## Scaricare / Download / Descargar

L'installer è nelle **[Releases](../../releases)**: `Biblioteca-Setup-<versione>.exe`. Windows 10 o 11 a 64 bit.

L'installer non è firmato: se Windows mostra *"Windows ha protetto il PC"*, premi **Ulteriori informazioni → Esegui comunque**.

The installer is in **Releases**. It is not code-signed: if Windows shows *"Windows protected your PC"*, choose **More info → Run anyway**.

El instalador está en **Releases**. No está firmado: si Windows muestra *"Windows protegió tu PC"*, pulsa **Más información → Ejecutar de todas formas**.

## Cosa fa / What it does / Qué hace

- **Inventario:** legge metadati e prime pagine; trova ISBN e codici a barre.
- **Doppioni:** distingue le copie identiche dalle edizioni diverse.
- **Proposte:** categoria, collezione, titolo e autore. Tu controlli e correggi.
- **Simulazione, esecuzione e verifica:** nulla viene spostato prima della tua conferma, e ogni esecuzione si può **annullare**.
- **Sicurezza:** non cancella mai nessun file. Le cartelle protette, come i backup, non vengono mai aperte.
- **Catalogo HTML** offline, con ricerca, temi e la sezione personale; **Excel** con inventario, piano ed elenco ISBN con codici a barre.
- **AI facoltativa**, da scegliere fra:
  - **sul PC** con llama.cpp e Qwen3.5: gratis e senza internet;
  - **Google Gemini:** gratis, senza carta di credito;
  - **Groq** o **Mistral:** con la propria chiave;
  - **Claude:** a pagamento.

  Ogni attivazione è guidata passo passo.

Il manuale completo (IT/EN/ES) è in [`biblioteca/risorse/manuale.html`](biblioteca/risorse/manuale.html).

## Per sviluppatori / For developers

You need Windows and Python 3.14:

```
python -m venv venv
venv\Scripts\pip install -r requirements.txt
venv\Scripts\python Biblioteca.pyw
```

To build the installer you also need:
- [Inno Setup 7](https://jrsoftware.org/isinfo.php);
- the Windows x64 **Vulkan** build of [llama.cpp](https://github.com/ggml-org/llama.cpp/releases) (b12015), unpacked into `installer/terzi/llama/`.

Then run:

```
powershell -ExecutionPolicy Bypass -File installer\build.ps1 -Python venv\Scripts\python.exe
```

`installer/licenze.py` writes `LICENZE.txt` with the licenses of every bundled library. It stops the build if it finds an AGPL or GPL-only dependency, such as PyMuPDF.

## Licenza / License / Licencia

[GNU GPL v3.0](LICENSE). Puoi usare, copiare, tradurre e modificare liberamente il programma; se lo ridistribuisci, anche modificato, deve restare libero e con il codice sorgente.

The bundled libraries keep their own licenses: MIT, BSD, Apache-2.0 and HPND. They are listed in `LICENZE.txt` inside the installed program. The AI models are not included; they are downloaded from Hugging Face under the Apache-2.0 license.
