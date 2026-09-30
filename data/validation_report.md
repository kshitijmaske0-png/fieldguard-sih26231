# Validation report (demo-swatch)

Photos: 48 total (24 tuning / 24 held-out test). Tuned on the tuning half: max_de=15, min_margin=2 (current kits.json: 12.0, 4.0).

| Condition | Correct | Wrong | Inconclusive | Retake | n |
|---|---|---|---|---|---|
| With colour correction (held-out) | 20 | 0 | 0 | 4 | 24 |
| Without colour correction (held-out) | 14 | 0 | 6 | 4 | 24 |

Per lighting, held-out, with correction (correct / attempted):

- daylight: 4/4 correct, 0 wrong, 0 inconclusive, 0 retake
- dim_indoor: 4/4 correct, 0 wrong, 0 inconclusive, 0 retake
- flash: 0/4 correct, 0 wrong, 0 inconclusive, 4 retake
- led_cool: 4/4 correct, 0 wrong, 0 inconclusive, 0 retake
- shadow: 4/4 correct, 0 wrong, 0 inconclusive, 0 retake
- warm_bulb: 4/4 correct, 0 wrong, 0 inconclusive, 0 retake

Notes: RETAKE and INCONCLUSIVE are safe outcomes, WRONG is not. Small samples give wide error margins; do not quote percentages without the sample size.
