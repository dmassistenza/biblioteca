"""Disegna l'icona del programma (tre libri in piedi, colori del catalogo) in biblioteca.ico, con tutte le misure."""
import os
import sys

from PIL import Image, ImageDraw


def disegna(n):
    s = 256
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([8, 8, s - 8, s - 8], radius=44, fill=(122, 75, 31, 255))  # marrone del catalogo
    libri = [(40, 70, 92, (241, 230, 216)), (98, 52, 150, (224, 168, 104)), (156, 84, 208, (246, 243, 238))]
    for x0, y0, x1, col in libri:
        d.rounded_rectangle([x0, y0, x1, 206], radius=8, fill=col + (255,))
        d.rectangle([x0 + 8, y0 + 22, x1 - 8, y0 + 30], fill=(122, 75, 31, 255))
        d.rectangle([x0 + 8, 176, x1 - 8, 184], fill=(122, 75, 31, 255))
    d.rounded_rectangle([30, 206, s - 30, 220], radius=5, fill=(241, 230, 216, 255))  # ripiano
    return img.resize((n, n), Image.LANCZOS)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "biblioteca.ico")
    grande = disegna(256)
    grande.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    grande.save(out.replace(".ico", ".png"))
    print(out)
