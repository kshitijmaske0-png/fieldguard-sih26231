"""Generate the printable reference card: assets/card.png (300 dpi) and assets/card.pdf.
Run from repo root:  python -m tools.make_card
Print at 100% scale (no 'fit to page') on matte paper. Then photograph one printed copy
in good daylight and run  python -m tools.calibrate card <photo>."""
import cv2
from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from backend import layout as L

DPI = 300
PX = DPI / 25.4


def p(v):
    return int(round(v * PX))


def render():
    w, h = p(L.CARD_MM[0]), p(L.CARD_MM[1])
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    aruco = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    side = p(L.MARKER_MM)
    for mid, (cx, cy) in L.MARKER_CENTRES_MM.items():
        m = cv2.aruco.generateImageMarker(aruco, mid, side, borderBits=1)
        img.paste(Image.fromarray(m).convert("RGB"), (p(cx) - side // 2, p(cy) - side // 2))
    try:
        f_big = ImageFont.load_default(size=44); f_small = ImageFont.load_default(size=30)
    except TypeError:
        f_big = f_small = ImageFont.load_default()
    d.text((p(105), p(12)), "FieldGuard reference card v1", fill=(0, 0, 0), font=f_big, anchor="mm")
    d.text((p(105), p(22)), "Keep flat, matte, clean. Do not fold. Print at 100%.", fill=(90, 90, 90), font=f_small, anchor="mm")
    pw, ph = L.PATCH_SIZE_MM
    for name, (rgb, cx, cy) in L.PATCHES.items():
        d.rectangle([p(cx - pw / 2), p(cy - ph / 2), p(cx + pw / 2), p(cy + ph / 2)], fill=rgb, outline=(0, 0, 0), width=2)
    sx, sy = L.SAMPLE_CENTRE_MM
    ww, wh = L.SAMPLE_WINDOW_MM
    d.rectangle([p(sx - ww / 2), p(sy - wh / 2), p(sx + ww / 2), p(sy + wh / 2)], outline=(0, 0, 0), width=4)
    r = p(L.SAMPLE_GUIDE_DIAM_MM / 2)
    d.ellipse([p(sx) - r, p(sy) - r, p(sx) + r, p(sy) + r], outline=(120, 120, 120), width=3)
    d.text((p(sx), p(sy - wh / 2 - 4)), "PLACE KIT (tube / pad) IN CIRCLE", fill=(0, 0, 0), font=f_small, anchor="mm")
    return img


if __name__ == "__main__":
    img = render()
    img.save("assets/card.png", dpi=(DPI, DPI))
    c = canvas.Canvas("assets/card.pdf", pagesize=(L.CARD_MM[0] * mm, L.CARD_MM[1] * mm))
    c.drawImage("assets/card.png", 0, 0, width=L.CARD_MM[0] * mm, height=L.CARD_MM[1] * mm)
    c.save()
    print("wrote assets/card.png and assets/card.pdf")
