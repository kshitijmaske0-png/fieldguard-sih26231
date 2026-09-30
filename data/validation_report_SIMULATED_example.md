# Validation report (demo-swatch)

Photos: 72 total (36 tuning / 36 held-out test). Tuned on the tuning half: max_de=15, min_margin=2 (current kits.json: 12.0, 4.0).

| Condition | Correct | Wrong | Inconclusive | Retake | n |
|---|---|---|---|---|---|
| With colour correction (held-out) | 30 | 0 | 0 | 6 | 36 |
| Without colour correction (held-out) | 21 | 0 | 9 | 6 | 36 |

Per lighting, held-out, with correction (correct / attempted):

- daylight: 6/6 correct, 0 wrong, 0 inconclusive, 0 retake
- dim_indoor: 6/6 correct, 0 wrong, 0 inconclusive, 0 retake
- flash: 0/6 correct, 0 wrong, 0 inconclusive, 6 retake
- led_cool: 6/6 correct, 0 wrong, 0 inconclusive, 0 retake
- shadow: 6/6 correct, 0 wrong, 0 inconclusive, 0 retake
- warm_bulb: 6/6 correct, 0 wrong, 0 inconclusive, 0 retake

Notes: RETAKE and INCONCLUSIVE are safe outcomes, WRONG is not. Small samples give wide error margins; do not quote percentages without the sample size.
