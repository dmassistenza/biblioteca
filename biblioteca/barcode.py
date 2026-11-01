"""Codice a barre EAN-13 dell'ISBN-13, come sul retro dei libri: disegno in PNG (Pillow) e rilettura
dai pixel, indipendente dal disegno, per controllare ogni codice prima di usarlo."""
import os

from PIL import Image, ImageDraw, ImageFont

L_CODE = ["0001101", "0011001", "0010011", "0111101", "0100011",
          "0110001", "0101111", "0111011", "0110111", "0001011"]
R_CODE = ["".join("1" if b == "0" else "0" for b in c) for c in L_CODE]
G_CODE = [c[::-1] for c in R_CODE]
PARITY = ["LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG",
          "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL"]

MOD = 3                  # pixel per modulo
QUIET_L, QUIET_R = 11, 7  # zone di rispetto in moduli
TOP, BAR_H, GUARD_EXTRA, TXT_H = 30, 120, 14, 30


def ean13_bits(code):
    first, left, right = int(code[0]), code[1:7], code[7:]
    bits = "101"
    for d, p in zip(left, PARITY[first]):
        bits += (L_CODE if p == "L" else G_CODE)[int(d)]
    bits += "01010"
    for d in right:
        bits += R_CODE[int(d)]
    return bits + "101"


def guard_positions():
    return set(range(0, 3)) | set(range(45, 50)) | set(range(92, 95))


def font(size):
    for f in (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\segoeui.ttf"):
        if os.path.exists(f):
            return ImageFont.truetype(f, size)
    return ImageFont.load_default(size)


def draw_barcode(code, path):
    bits = ean13_bits(code)
    w = (QUIET_L + 95 + QUIET_R) * MOD
    h = TOP + BAR_H + GUARD_EXTRA + TXT_H - 10
    img = Image.new("L", (w, h), 255)
    d = ImageDraw.Draw(img)
    guards = guard_positions()
    for i, b in enumerate(bits):
        if b == "1":
            x = (QUIET_L + i) * MOD
            y2 = TOP + BAR_H + (GUARD_EXTRA if i in guards else 0)
            d.rectangle([x, TOP, x + MOD - 1, y2 - 1], fill=0)
    small, big = font(20), font(26)
    d.text((w / 2, 4), "ISBN " + code, font=small, fill=0, anchor="ma")
    ty = TOP + BAR_H + 1
    d.text(((QUIET_L - 1) * MOD, ty), code[0], font=big, fill=0, anchor="ra")
    d.text(((QUIET_L + 3 + 21) * MOD, ty), code[1:7], font=big, fill=0, anchor="ma")
    d.text(((QUIET_L + 50 + 21) * MOD, ty), code[7:], font=big, fill=0, anchor="ma")
    img.save(path, optimize=True)


def decode_barcode(path):
    """Rilegge l'EAN-13 dai pixel (riga a meta' delle barre), indipendente dal disegno."""
    img = Image.open(path).convert("L")
    y = TOP + BAR_H // 2
    row = [img.getpixel((x, y)) < 128 for x in range(img.width)]
    xs = [x for x, v in enumerate(row) if v]
    if not xs:
        return None
    start, end = xs[0], xs[-1] + 1
    mod = (end - start) / 95
    bits = "".join("1" if row[int(start + (i + 0.5) * mod)] else "0" for i in range(95))
    if bits[:3] != "101" or bits[45:50] != "01010" or bits[92:] != "101":
        return None
    digits, par = "", ""
    for k in range(6):
        c = bits[3 + 7 * k: 10 + 7 * k]
        if c in L_CODE:
            digits += str(L_CODE.index(c)); par += "L"
        elif c in G_CODE:
            digits += str(G_CODE.index(c)); par += "G"
        else:
            return None
    for k in range(6):
        c = bits[50 + 7 * k: 57 + 7 * k]
        if c not in R_CODE:
            return None
        digits += str(R_CODE.index(c))
    if par not in PARITY:
        return None
    code = str(PARITY.index(par)) + digits
    ok = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(code)) % 10 == 0
    return code if ok else None
