# FieldGuard (SIH26231)

Mobile-first web app that reads a colorimetric test kit next to a printed reference card and stores the
result as a **signed, hash-chained record** with a public verify page. The result is **presumptive**:
laboratory confirmation is still required.

```
Phone browser (plain JS PWA, frontend/)  --HTTPS-->  FastAPI (backend/main.py)
                                                       |- vision.py   card detection, colour correction, classification
                                                       |- records.py  canonical JSON, SHA-256, Ed25519, hash chain
                                                       |- service.py  rules (expired kit, control step, timer), verify
                                                       |- db.py       SQLite (users, tests) + chain lock
                                                       |- report.py   PDF + QR
                                                       `- data/uploads  original JPEGs, never edited
```

## Live demo

URL: [Pending Deployment]

## Run it (5 minutes)

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
python -m tools.make_card                              # writes assets/card.pdf (print this, 100% scale, matte paper)
export FIELDGUARD_DEMO_PASSWORD='choose-something'     # Windows PowerShell: $env:FIELDGUARD_DEMO_PASSWORD='...'
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```
Open http://localhost:8000, log in as `officer1` / `officer2` / `officer3` with that password
(if you do not set it, a random one is printed once in the server console).

Phone camera and GPS need **HTTPS**. For phone testing run `cloudflared tunnel --url http://localhost:8000`
(or ngrok) and open the https link on the phone; "Add to home screen" installs it.

## Before you rely on any result (do these in order)

1. **Print the card** (`assets/card.pdf`). Keep one clean copy as the golden reference.
2. **Calibrate the card**: photograph the golden card in good daylight, then
   `python -m tools.calibrate card photo.jpg`. Until you do, the app uses the design colours and every
   record says `card_calibrated: false`.
3. **Pick ONE kit.** Edit `data/kits.json`: reading window from the leaflet, then for each outcome colour on the
   kit's own chart, place it in the card's circle, photograph it and run
   `python -m tools.calibrate kitclass photo.jpg <kit_id> <class_name>`.
   The shipped `demo-swatch` colours are **placeholders, not real chemistry**.
4. **Validate** (Step 9): put 30 to 60 real photos in `data/test_photos/` with `labels.csv`
   (`file,true_class,lighting`), then `python -m tools.validate`. Quote the numbers with the sample size.
   No real photos yet? `python -m tools.simulate` makes simulated ones (say "simulated" in the demo).

## Rules the server enforces
Expired kit blocked, control step required, reading window must be completed, JPEG/PNG only, server sets the
timestamp, exact uploaded bytes are hashed, chain insert is locked, RETAKE results are **not** stored
(bad card visibility, blur, over/under-exposure, glare, uneven light, off-centre sample).

## API (all under /api)
`POST auth/login` · `GET me` · `GET kits` · `POST tests` (multipart) · `GET tests?q=&result=&operator=&date_from=&date_to=` ·
`GET tests/{id}` · `GET tests/{id}/image|annotated|report.pdf` · public: `GET verify/{id}`, `GET verify-chain`, `GET pubkey`.
The QR code in the PDF points to `/#/verify/{id}` (public page, no login).

## Configuration (environment variables)
| Variable | Purpose |
|---|---|
| `FIELDGUARD_SIGNING_KEY` | 64 hex chars (Ed25519 seed). Make one: `python -m backend.records genkey`. **Set it in production.** |
| `FIELDGUARD_JWT_SECRET` | any long random string |
| `FIELDGUARD_DEMO_PASSWORD` | password for the 3 seeded officers |
| `FIELDGUARD_DATA_DIR` | where the DB and uploads live (mount persistent storage) |

If the signing key or JWT secret is missing, a dev secret is generated inside `data/` (git-ignored) and a warning
is printed. Never commit keys. If you lose the signing key, old records can no longer be verified.

## Demo tamper test (step 6 of the demo script)
Work on a copy: `cp -r data data_copy && FIELDGUARD_DATA_DIR=data_copy uvicorn backend.main:app`, then
`FIELDGUARD_DATA_DIR=data_copy python -m tools.tamper_demo <record_id>` and refresh the verify page: INVALID.
`--restore` puts it back. Deleting a record in the middle is caught by the next record's chain link.

## Tests
`python -m unittest -v` runs 6 end-to-end tests (result, chain, blocks, RETAKE, tamper, deleted record, swapped
image, search, PDF) against simulated photos.

## Honest limits (keep these on your slides)
- Presumptive colour match; match score is not a probability; no "95% accurate" without your own measured numbers.
- Tamper-evident, not tamper-proof: the server signs, so this shows changes after the fact, not that the server was
  honest. Deleting the **newest** record is not detectable without external anchoring (RFC 3161, planned).
- GPS and device time are metadata and can be spoofed. In-app capture reduces gallery uploads; it is not a hardware guarantee.
- Planned, not built: offline sync, external timestamp anchoring, lab-result feedback, roles, more kits, Hindi/Marathi UI.

## Differences from the build guide
Frontend is plain JS with no build step (no Node/Vite needed; same screens). The QR code uses ReportLab's built-in
generator, so the `qrcode` package is not needed. API routes are prefixed with `/api`.
