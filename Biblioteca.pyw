"""Avvio del programma Biblioteca (finestra, senza console). PyInstaller parte da qui.
Biblioteca.exe --verifica <file.json>  -> autoverifica senza finestra (vedi app.verifica)."""
import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()  # nell'.exe i processi dell'analisi rientrano da qui
    if len(sys.argv) > 2 and sys.argv[1] == "--verifica":
        from biblioteca.app import verifica
        verifica(sys.argv[2])
    else:
        from biblioteca.app import main
        main()
