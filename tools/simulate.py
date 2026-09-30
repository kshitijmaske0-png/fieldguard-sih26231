"""Generate SIMULATED phone photos of the card + a coloured swatch under different lighting.
Useful to (a) test the pipeline before you have real kits and (b) fill data/test_photos
for Step 9. Say plainly in the demo that this data is simulated. Real photos are better:
put them in data/test_photos/ with a labels.csv (file,true_class,lighting).

  python -m tools.simulate --kit demo-swatch --per-cell 4
"""
import argparse, csv, json
from pathlib import Path
import cv2
import numpy as np
from backend import layout as L
from backend.config import KITS_PATH

ROOT = Path(__file__).resolve().parent.parent
# lighting: (per-channel RGB gain, gamma, brightness multiplier, shadow strength 0..1, noise sigma)
LIGHTING = {
    "daylight":   ((1.00, 1.00, 1.00), 1.00, 1.00, 0.00, 2.0),
    "led_cool":   ((0.90, 1.00, 1.15), 1.00, 0.95, 0.00, 3.0),
    "warm_bulb":  ((1.15, 1.00, 0.78), 1.00, 0.90, 0.00, 3.0),
    "dim_indoor": ((1.05, 1.00, 0.90), 1.10, 0.55, 0.00, 5.0),
    "shadow":     ((1.00, 1.00, 1.00), 1.00, 0.95, 0.55, 3.0),
    "flash":      ((1.05, 1.02, 1.00), 0.85, 1.75, 0.00, 2.0),
}


def render(class_rgb, lighting="daylight", seed=0, size=(1600, 1200), tilt=0.06, blur=0.0, print_shift=True):
    rng = np.random.default_rng(seed)
    card = cv2.imread(str(ROOT / "assets" / "card.png"))
    s = 1250 / card.shape[1]
    card = cv2.resize(card, None, fx=s, fy=s, interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
    if print_shift:                       # printed colours are never the design colours
        card = np.clip(card * np.array([0.95, 0.97, 0.93]) + 0.02, 0, 1)
    ppm = 1250 / L.CARD_MM[0]
    if class_rgb is not None:            # kit swatch drawn as a physical object (not printed)
        cx, cy = int(L.SAMPLE_CENTRE_MM[0] * ppm), int(L.SAMPLE_CENTRE_MM[1] * ppm)
        r = int(10 * ppm)
        bgr = tuple(float(c) for c in class_rgb[::-1])
        cv2.circle(card, (cx, cy), r, bgr, -1, cv2.LINE_AA)
    h, w = card.shape[:2]
    bg = np.full((size[1], size[0], 3), 0.18, np.float32)
    jit = lambda: rng.uniform(-tilt, tilt)
    off = np.float32([(size[0] - w) / 2, (size[1] - h) / 2])
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = src + off + np.float32([[w * jit(), h * jit()] for _ in range(4)])
    M = cv2.getPerspectiveTransform(src, dst)
    mask = cv2.warpPerspective(np.ones((h, w), np.float32), M, size)[..., None]
    img = cv2.warpPerspective(card, M, size, borderValue=(0, 0, 0)) + (1 - mask) * bg
    gain, gamma, bright, shadow, sigma = LIGHTING[lighting]
    img = np.clip(img, 0, 1) ** gamma * np.array(gain[::-1], np.float32) * bright     # BGR gains
    if shadow > 0:                       # diagonal shadow band over part of the scene
        yy, xx = np.mgrid[0:size[1], 0:size[0]]
        ramp = np.clip((xx / size[0] + yy / size[1] - 0.9) / 0.5, 0, 1)[..., None]
        img = img * (1 - shadow * ramp)
    if blur:
        img = cv2.GaussianBlur(img, (0, 0), blur)
    img = np.clip(img + rng.normal(0, sigma / 255.0, img.shape), 0, 1)
    ok, buf = cv2.imencode(".jpg", (img * 255).astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 92])
    return buf.tobytes()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kit", default="demo-swatch")
    ap.add_argument("--per-cell", type=int, default=4)
    ap.add_argument("--out", default=str(ROOT / "data" / "test_photos"))
    a = ap.parse_args()
    kit = json.loads(KITS_PATH.read_text())["kits"][a.kit]
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    rows, n = [], 0
    for cls, rgb in kit["classes"].items():
        for light in LIGHTING:
            for k in range(a.per_cell):
                n += 1
                rng = np.random.default_rng(1000 + n)
                jittered = np.clip(np.array(rgb) + rng.normal(0, 0.012, 3), 0, 1)
                name = f"sim_{cls}_{light}_{k}.jpg"
                (out / name).write_bytes(render(jittered, light, seed=n))
                rows.append((name, cls.upper(), light))
    with open(out / "labels.csv", "w", newline="") as f:
        wr = csv.writer(f); wr.writerow(["file", "true_class", "lighting"]); wr.writerows(rows)
    print(f"wrote {len(rows)} simulated photos + labels.csv to {out}")


if __name__ == "__main__":
    main()
