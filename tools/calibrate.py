"""Measure real reference colours from photos and store them.

  python -m tools.calibrate card <photo_of_printed_card_in_good_daylight>
      -> data/card_reference.json  (what the printed patches really look like)
  python -m tools.calibrate kitclass <photo> <kit_id> <class_name>
      -> updates data/kits.json for that class (photograph the kit's colour chart or
         swatch inside the card's sample circle, in good light, AFTER calibrating the card)

Do not invent chemistry: use your kit's own chart/leaflet colours.
"""
import sys, json
import numpy as np
from backend import layout as L, vision
from backend.config import CARD_REF_PATH, KITS_PATH


def measure_card(path):
    img = vision.decode(open(path, "rb").read())
    flat = vision.warp_card(img)
    if flat is None:
        sys.exit("Could not find all 4 markers in the photo.")
    return {n: [round(float(c), 5) for c in vision.median_rgb01(flat, *L.mm_to_px(v[1], v[2]), r=L.PATCH_READ_R_PX)]
            for n, v in L.PATCHES.items()}


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "card":
        patches = measure_card(sys.argv[2])
        CARD_REF_PATH.write_text(json.dumps({"version": "card-v1-measured", "patches": patches}, indent=2))
        print("saved", CARD_REF_PATH)
    elif len(sys.argv) == 5 and sys.argv[1] == "kitclass":
        _, _, photo, kit_id, cls = sys.argv
        data = open(photo, "rb").read()
        kits = json.loads(KITS_PATH.read_text())
        kit = kits["kits"][kit_id]
        res = vision.analyse(data, {**kit, "classes": {"x": [0, 0, 0]}}, want_annotated=False)
        if res["status"] != "OK":
            sys.exit(f"Retake needed: {res['reason']}")
        kit["classes"][cls] = [round(c, 4) for c in res["sample_rgb"]]
        kit["calibrated"] = True
        KITS_PATH.write_text(json.dumps(kits, indent=2))
        print(f"{kit_id}/{cls} = {kit['classes'][cls]}")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
