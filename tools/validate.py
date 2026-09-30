"""Step 9: honest accuracy numbers. Reads data/test_photos/labels.csv (file,true_class,lighting),
runs the pipeline WITH and WITHOUT colour correction, tunes max_de/min_margin on one half and
reports on the other half.  Writes data/validation_report.md.

  python -m tools.validate --kit demo-swatch
Report the sample size next to every number, and say whether photos are real or simulated."""
import argparse, csv, itertools, json
from collections import Counter
from pathlib import Path
from backend import vision
from backend.config import KITS_PATH

ROOT = Path(__file__).resolve().parent.parent


def outcome(res, true_cls, kit, max_de, min_margin):
    if res["status"] != "OK":
        return "RETAKE"
    pred, _ = vision.classify(res["sample_rgb"], kit["classes"], max_de, min_margin)
    return "CORRECT" if pred == true_cls else ("INCONCLUSIVE" if pred == "INCONCLUSIVE" else "WRONG")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--kit", default="demo-swatch")
    ap.add_argument("--dir", default=str(ROOT / "data" / "test_photos")); a = ap.parse_args()
    kit = json.loads(KITS_PATH.read_text())["kits"][a.kit]
    rows = list(csv.DictReader(open(Path(a.dir) / "labels.csv")))
    tune, test = rows[0::2], rows[1::2]
    cache = {}
    for corr in (True, False):
        for r in rows:
            cache[(corr, r["file"])] = vision.analyse((Path(a.dir) / r["file"]).read_bytes(), kit,
                                                      use_correction=corr, want_annotated=False)
    grid = list(itertools.product([6, 8, 10, 12, 15, 20], [2, 4, 6, 8]))

    def tally(subset, corr, mde, mm):
        return Counter(outcome(cache[(corr, r["file"])], r["true_class"], kit, mde, mm) for r in subset)

    def objective(c): return c["CORRECT"] - 3 * c["WRONG"]
    best = max(grid, key=lambda g: objective(tally(tune, True, *g)))
    out = [f"# Validation report ({a.kit})", "", f"Photos: {len(rows)} total ({len(tune)} tuning / {len(test)} held-out test). "
           f"Tuned on the tuning half: max_de={best[0]}, min_margin={best[1]} (current kits.json: "
           f"{kit.get('max_de')}, {kit.get('min_margin')}).", "",
           "| Condition | Correct | Wrong | Inconclusive | Retake | n |", "|---|---|---|---|---|---|"]
    for label, corr in (("With colour correction", True), ("Without colour correction", False)):
        c = tally(test, corr, *best)
        out.append(f"| {label} (held-out) | {c['CORRECT']} | {c['WRONG']} | {c['INCONCLUSIVE']} | {c['RETAKE']} | {len(test)} |")
    out += ["", "Per lighting, held-out, with correction (correct / attempted):", ""]
    for light in sorted({r["lighting"] for r in test}):
        sub = [r for r in test if r["lighting"] == light]
        c = tally(sub, True, *best)
        out.append(f"- {light}: {c['CORRECT']}/{len(sub)} correct, {c['WRONG']} wrong, {c['INCONCLUSIVE']} inconclusive, {c['RETAKE']} retake")
    out += ["", "Notes: RETAKE and INCONCLUSIVE are safe outcomes, WRONG is not. Small samples give wide error "
            "margins; do not quote percentages without the sample size."]
    (ROOT / "data" / "validation_report.md").write_text("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
