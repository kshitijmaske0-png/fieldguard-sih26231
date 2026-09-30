"""Card detection, colour correction and classification.

The output is a PRESUMPTIVE colour match against stored reference colours. It is not a
chemical identification and does not replace laboratory confirmation.
"""
import json
import cv2
import numpy as np
from skimage.color import rgb2lab, deltaE_ciede2000

from . import layout as L
from .config import CARD_REF_PATH

ARUCO = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)

# Quality thresholds: starting values, tune on your own photos (tools/validate.py).
MIN_MARKER_PX = 40           # smallest marker side in the photo
BLUR_MIN = 60.0              # Laplacian variance of the flattened card
WHITE_RANGE = (0.35, 0.985)  # raw white-patch brightness (0..1)
BLACK_MAX = 0.40             # raw black-patch brightness
CLIP_MAX = 0.15              # fraction of white-patch pixels at 255
CARD_DE_MAX = 8.0            # mean deltaE2000 on the card patches after correction
SAMPLE_STD_MAX = 6.0         # colour spread inside the sample circle after correction


def nominal_card_reference():
    return {"version": "nominal", "calibrated": False,
            "patches": {k: [c / 255.0 for c in v[0]] for k, v in L.PATCHES.items()}}


def load_card_reference():
    if CARD_REF_PATH.exists():
        ref = json.loads(CARD_REF_PATH.read_text())
        ref["calibrated"] = True
        return ref
    return nominal_card_reference()


def decode(image_bytes):
    arr = np.frombuffer(image_bytes, np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def detect_markers(img_bgr):
    det = cv2.aruco.ArucoDetector(ARUCO, cv2.aruco.DetectorParameters())
    corners, ids, _ = det.detectMarkers(img_bgr)
    if ids is None:
        return None, 0.0
    pts, sides = {}, []
    for i, c in zip(ids.flatten(), corners):
        pts[int(i)] = c[0].mean(axis=0)
        sides.append(float(np.linalg.norm(c[0][0] - c[0][1])))
    if not all(k in pts for k in (0, 1, 2, 3)):
        return None, 0.0
    return pts, min(sides)


def warp_card(img_bgr, pts=None):
    if pts is None:
        pts, _ = detect_markers(img_bgr)
    if pts is None:
        return None
    src = np.float32([pts[0], pts[1], pts[2], pts[3]])          # TL, TR, BR, BL
    dst = np.float32([[0, 0], [L.CARD_W, 0], [L.CARD_W, L.CARD_H], [0, L.CARD_H]])
    M = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(img_bgr, M, (L.CARD_W, L.CARD_H))


def _roi(img_bgr, x, y, r):
    h, w = img_bgr.shape[:2]
    x0, x1, y0, y1 = max(x - r, 0), min(x + r, w), max(y - r, 0), min(y + r, h)
    return img_bgr[y0:y1, x0:x1].reshape(-1, 3)


def median_rgb01(img_bgr, x, y, r=15):
    return np.median(_roi(img_bgr, x, y, r), axis=0)[::-1] / 255.0      # BGR -> RGB, 0..1


def fit_correction(measured, reference):
    """Least-squares affine colour correction. measured/reference: Nx3 arrays."""
    A = np.hstack([measured, np.ones((len(measured), 1))])
    X, *_ = np.linalg.lstsq(A, reference, rcond=None)
    return X                                                            # 4x3


def apply_correction(rgb, X):
    return np.clip(np.append(rgb, 1.0) @ X, 0, 1)


def de(rgb_a, rgb_b):
    la = rgb2lab(np.array(rgb_a, dtype=float).reshape(1, 1, 3))
    lb = rgb2lab(np.array(rgb_b, dtype=float).reshape(1, 1, 3))
    return float(deltaE_ciede2000(la, lb)[0, 0])


def classify(sample_rgb, class_refs, max_de=12.0, min_margin=4.0):
    """class_refs = {'negative': [r,g,b], 'positive': [r,g,b]} (0..1)."""
    scores = {k: de(sample_rgb, v) for k, v in class_refs.items()}
    ranked = sorted(scores.items(), key=lambda kv: kv[1])
    best, d1 = ranked[0]
    d2 = ranked[1][1] if len(ranked) > 1 else float("inf")
    if d1 > max_de or (d2 - d1) < min_margin:
        return "INCONCLUSIVE", scores
    return best.upper(), scores


def _retake(reason, **extra):
    return {"status": "RETAKE", "reason": reason, **extra}


def analyse(image_bytes, kit, card_ref=None, use_correction=True, want_annotated=True):
    """Returns a dict. status is 'OK' or 'RETAKE'. On OK it has result (POSITIVE, NEGATIVE,
    other kit-defined classes, or INCONCLUSIVE), match_score, colour_scores, quality."""
    card_ref = card_ref or load_card_reference()
    img = decode(image_bytes)
    if img is None:
        return _retake("Image could not be read")
    pts, marker_px = detect_markers(img)
    if pts is None:
        return _retake("Card not fully visible: all four corner markers must be in frame")
    if marker_px < MIN_MARKER_PX:
        return _retake("Card too far away: move closer so the card fills the frame")
    flat = warp_card(img, pts)

    q = {"marker_px": round(marker_px, 1)}
    gray = cv2.cvtColor(flat, cv2.COLOR_BGR2GRAY)
    q["blur_var"] = round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 1)
    if q["blur_var"] < BLUR_MIN:
        return _retake("Photo is blurry: hold steady and let the camera focus", quality=q)

    names = list(L.PATCHES.keys())
    measured = np.array([median_rgb01(flat, *L.mm_to_px(L.PATCHES[n][1], L.PATCHES[n][2]),
                                      r=L.PATCH_READ_R_PX) for n in names])
    reference = np.array([card_ref["patches"][n] for n in names])
    wi, bi = names.index("white"), names.index("black")
    q["white_level"], q["black_level"] = round(float(measured[wi].mean()), 3), round(float(measured[bi].mean()), 3)
    wx, wy = L.mm_to_px(L.PATCHES["white"][1], L.PATCHES["white"][2])
    q["white_clipped"] = round(float((_roi(flat, wx, wy, L.PATCH_READ_R_PX) >= 250).all(axis=1).mean()), 3)
    if q["white_level"] < WHITE_RANGE[0]:
        return _retake("Too dark: move to better light", quality=q)
    if q["white_level"] > WHITE_RANGE[1] or q["white_clipped"] > CLIP_MAX:
        return _retake("Overexposed or glare on the card: avoid flash and direct reflections", quality=q)
    if q["black_level"] > BLACK_MAX:
        return _retake("Washed out: reduce glare or strong backlight", quality=q)

    X = fit_correction(measured, reference) if use_correction else np.vstack([np.eye(3), np.zeros((1, 3))])
    corrected = np.array([apply_correction(m, X) for m in measured])
    q["card_de_mean"] = round(float(np.mean([de(c, r) for c, r in zip(corrected, reference)])), 2)
    if use_correction and q["card_de_mean"] > CARD_DE_MAX:
        return _retake("Lighting is uneven or the card is dirty/creased: retake in even light", quality=q)

    sx, sy = L.mm_to_px(*L.SAMPLE_CENTRE_MM)
    roi_rgb = _roi(flat, sx, sy, L.SAMPLE_READ_R_PX)[:, ::-1] / 255.0
    corr_px = np.clip(np.hstack([roi_rgb, np.ones((len(roi_rgb), 1))]) @ X, 0, 1)
    lab = rgb2lab(corr_px.reshape(-1, 1, 3)).reshape(-1, 3)
    q["sample_std"] = round(float(np.sqrt(lab.var(axis=0).sum())), 2)
    if q["sample_std"] > SAMPLE_STD_MAX:
        return _retake("Sample area is not uniform: centre the kit in the circle", quality=q)
    sample = apply_correction(median_rgb01(flat, sx, sy, r=L.SAMPLE_READ_R_PX), X)

    result, scores = classify(sample, kit["classes"], kit.get("max_de", 12.0), kit.get("min_margin", 4.0))
    best = min(scores.values())
    match = float(np.clip(1 - best / kit.get("max_de", 12.0), 0, 1))
    out = {"status": "OK", "result": result, "match_score": round(match, 3),
           "colour_scores": {k: round(v, 2) for k, v in scores.items()},
           "sample_rgb": [round(float(c), 4) for c in sample], "quality": q,
           "colour_correction": bool(use_correction), "card_calibrated": bool(card_ref.get("calibrated"))}
    if want_annotated:
        ann = flat.copy()
        for n in names:
            cv2.circle(ann, L.mm_to_px(L.PATCHES[n][1], L.PATCHES[n][2]), L.PATCH_READ_R_PX, (0, 200, 0), 2)
        cv2.circle(ann, (sx, sy), L.SAMPLE_READ_R_PX, (0, 0, 255), 3)
        cv2.putText(ann, f"{result} match={match:.2f}", (20, L.CARD_H - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
        ok, buf = cv2.imencode(".jpg", ann, [cv2.IMWRITE_JPEG_QUALITY, 90])
        out["_annotated_jpeg"] = buf.tobytes() if ok else None
    return out
